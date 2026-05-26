"""ACBC market simulation — share-of-preference + RFC + removal impact.

After fitting ACBC utilities (MNL population or HB per-respondent) we
can simulate the market by predicting how a respondent would *choose*
among a set of competing products. Two common models are supported:

* :func:`share_of_preference` — deterministic logit-share formula
  ``Share_j = exp(α·U_j) / Σ exp(α·U_k)``. Fast and analytic; ``α``
  controls the choice "temperature".
* :func:`randomized_first_choice` — Monte-Carlo simulation with
  Gumbel-distributed noise on top of the systematic utility; the chosen
  alt is the argmax (i.e. the empirical "first choice"). Matches
  Sawtooth's RFC method.

:func:`removal_impact` runs the chosen model twice — once on the full
product set, once with selected products removed — and reports the
share transfer (who absorbed the removed share).

The module is dependency-light (numpy + pandas + standard library).
Inputs are utility dictionaries `{attribute: {level_code: float}}`
plus product specs `{product_id: {attribute: level_code}}`; the
functions are agnostic to whether utilities come from MNL or HB.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

#: Per-respondent utilities: ``{attribute: {level_code: utility}}``.
PerLevelUtilities = Mapping[str, Mapping[str, float]]
#: A product = ``{attribute: level_code}``.
ProductSpec = Mapping[str, str]


def product_utility(
    product: ProductSpec,
    utilities: PerLevelUtilities,
) -> float:
    """Sum of part-worth utilities for the levels in ``product``."""
    total = 0.0
    for attribute, code in product.items():
        per_level = utilities.get(attribute)
        if per_level is None:
            continue
        total += float(per_level.get(code, 0.0))
    return total


def share_of_preference(
    utilities: PerLevelUtilities,
    products: Mapping[str, ProductSpec],
    *,
    alpha: float = 1.0,
) -> "OrderedDict[str, float]":
    """Deterministic logit share for a single respondent's utilities.

    Numerically stable: subtracts the max utility before exponentiation.
    """
    if not products:
        raise ValueError("at least one product required")
    raw = OrderedDict(
        (product_id, product_utility(spec, utilities))
        for product_id, spec in products.items()
    )
    values = np.array(list(raw.values()), dtype=float)
    scaled = alpha * (values - values.max())
    exps = np.exp(scaled)
    total = exps.sum()
    if total <= 0:
        raise ValueError("share denominator collapsed to zero")
    return OrderedDict(zip(raw.keys(), (exps / total).tolist()))


def randomized_first_choice(
    utilities: PerLevelUtilities,
    products: Mapping[str, ProductSpec],
    *,
    n_draws: int = 1000,
    gumbel_scale: float = 1.0,
    seed: int | None = None,
) -> "OrderedDict[str, float]":
    """Monte-Carlo share via Gumbel-perturbed first-choice draws."""
    if n_draws <= 0:
        raise ValueError(f"n_draws must be positive (got {n_draws})")
    raw = np.array(
        [product_utility(spec, utilities) for spec in products.values()],
        dtype=float,
    )
    rng = np.random.default_rng(seed)
    perturbed = raw[None, :] + gumbel_scale * rng.gumbel(size=(n_draws, raw.shape[0]))
    chosen = perturbed.argmax(axis=1)
    counts = np.bincount(chosen, minlength=raw.shape[0])
    shares = counts / float(n_draws)
    return OrderedDict(zip(products.keys(), shares.tolist()))


def aggregate_shares(
    per_respondent_shares: Sequence[Mapping[str, float]],
) -> "OrderedDict[str, float]":
    """Mean share across respondents (Sawtooth's "market share" output)."""
    if not per_respondent_shares:
        raise ValueError("at least one respondent share dict required")
    keys = list(per_respondent_shares[0].keys())
    totals = np.zeros(len(keys))
    for shares in per_respondent_shares:
        for idx, key in enumerate(keys):
            totals[idx] += float(shares.get(key, 0.0))
    totals /= float(len(per_respondent_shares))
    return OrderedDict(zip(keys, totals.tolist()))


@dataclass(frozen=True)
class RemovalImpact:
    """Result of simulating one or more product removals."""

    before_shares: "OrderedDict[str, float]"
    after_shares: "OrderedDict[str, float]"
    removed: tuple[str, ...]
    transfer: pd.DataFrame    # one row per product, columns: before/after/delta


def _shares_from_utilities(
    utilities: PerLevelUtilities,
    products: Mapping[str, ProductSpec],
    *,
    model: str,
    alpha: float,
    gumbel_scale: float,
    n_draws: int,
    seed: int | None,
) -> "OrderedDict[str, float]":
    if model == "logit":
        return share_of_preference(utilities, products, alpha=alpha)
    if model == "rfc":
        return randomized_first_choice(
            utilities,
            products,
            n_draws=n_draws,
            gumbel_scale=gumbel_scale,
            seed=seed,
        )
    raise ValueError(f"unknown share model {model!r}")


def removal_impact(
    utilities_by_respondent: Sequence[PerLevelUtilities],
    products: Mapping[str, ProductSpec],
    to_remove: Sequence[str],
    *,
    model: str = "logit",
    alpha: float = 1.0,
    gumbel_scale: float = 1.0,
    n_draws: int = 1000,
    seed: int | None = None,
) -> RemovalImpact:
    """Simulate market shares before vs after removing ``to_remove``.

    The simulation is run per respondent and averaged; ``transfer``
    carries one row per surviving product with the share delta
    (positive ⇒ this product *absorbed* part of the removed share).
    """
    if not utilities_by_respondent:
        raise ValueError("at least one respondent's utilities required")
    if not products:
        raise ValueError("products mapping must be non-empty")
    removed = tuple(to_remove)
    bad = [pid for pid in removed if pid not in products]
    if bad:
        raise ValueError(f"removal references unknown product(s): {bad}")

    before_per_resp = []
    after_per_resp = []
    surviving = OrderedDict(
        (pid, spec) for pid, spec in products.items() if pid not in removed
    )
    if not surviving:
        raise ValueError("cannot remove every product")

    for utilities in utilities_by_respondent:
        before_per_resp.append(
            _shares_from_utilities(
                utilities, products,
                model=model, alpha=alpha, gumbel_scale=gumbel_scale,
                n_draws=n_draws, seed=seed,
            )
        )
        after_per_resp.append(
            _shares_from_utilities(
                utilities, surviving,
                model=model, alpha=alpha, gumbel_scale=gumbel_scale,
                n_draws=n_draws, seed=seed,
            )
        )
    before = aggregate_shares(before_per_resp)
    after = aggregate_shares(after_per_resp)

    transfer_rows: list[dict[str, object]] = []
    for product_id in products:
        before_share = float(before.get(product_id, 0.0))
        after_share = float(after.get(product_id, 0.0))
        delta = after_share - before_share
        transfer_rows.append(
            {
                "product": product_id,
                "removed": product_id in removed,
                "share_before": before_share,
                "share_after": after_share,
                "delta": delta,
            }
        )
    transfer = pd.DataFrame(transfer_rows)
    return RemovalImpact(
        before_shares=before,
        after_shares=after,
        removed=removed,
        transfer=transfer,
    )


def utilities_from_frame(
    frame: pd.DataFrame,
    level_map: Mapping[str, Sequence[str]],
) -> list["OrderedDict[str, OrderedDict[str, float]]"]:
    """Convert a wide utilities frame (per-respondent rows) into dicts.

    Accepts the output of :func:`conjoint.acbc.estimate.hb_to_utilities`
    or :func:`conjoint.estimate.estimate_utilities`.
    """
    rows: list["OrderedDict[str, OrderedDict[str, float]]"] = []
    for _, row in frame.iterrows():
        utilities: "OrderedDict[str, OrderedDict[str, float]]" = OrderedDict()
        for attribute, codes in level_map.items():
            per_level: "OrderedDict[str, float]" = OrderedDict()
            for code in codes:
                column = f"{attribute}__{code}"
                if column not in frame.columns:
                    continue
                per_level[code] = float(row[column])
            utilities[attribute] = per_level
        rows.append(utilities)
    return rows
