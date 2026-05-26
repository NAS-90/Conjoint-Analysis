"""ACBC MNL estimation — log-likelihood, L-BFGS fit, RLH, importance.

Implements the §3 ACBC estimation step using the standard discrete-choice
specification (McFadden 1974):

* Utility ``U_{i,t,j} = X_{t,j} · β_i + ε`` (Gumbel) ⇒
  ``P(choose j) = exp(X·β) / Σ_k exp(X·β)``.
* Effects coding (see :mod:`conjoint.acbc.design`) so the dropped level
  per attribute has utility ``-Σ`` of its surviving betas.
* Log-likelihood is summed over all (respondent, task) Tournament rows;
  ``y`` is the chosen-alt indicator.
* ``scipy.optimize.minimize`` (L-BFGS-B) finds the MLE for population
  betas. The per-respondent HB extension lives in Phase 4.
* Root Likelihood (RLH) = ``exp(LL/T)`` — the geometric mean of choice
  probabilities, used by Sawtooth to spot inattentive respondents.
* :func:`attribute_importance` recovers each attribute's Range_A and
  emits an ``importance.csv`` with **exactly the columns
  :mod:`conjoint.io` already writes**, so downstream
  :mod:`compute_distance_matrix` works without any change.

CLI: ``python -m conjoint.acbc.estimate --responses acbc_responses.csv
--out-importance importance.csv``.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.design import Profile, effects_code
from conjoint.acbc.responses import (
    ALTERNATIVE_INDEX_COL,
    CHOSEN_COL,
    RESPONDENT_COL,
    STAGE_COL,
    STAGE_TOURNAMENT,
    TASK_ID_COL,
)
from conjoint.io import (
    ABSOLUTE_IMPORTANCE_COL,
    ATTRIBUTE_COL,
    IMPORTANCE_COLUMNS,
    PathLike,
    RELATIVE_IMPORTANCE_COL,
    write_importance,
)

logger = logging.getLogger(__name__)

#: A converged fit, returned by :func:`fit_mnl`.
@dataclass(frozen=True)
class MNLFit:
    """Result of fitting a population-level MNL."""

    beta: np.ndarray          # shape (n_features,)
    log_likelihood: float
    n_tasks: int
    column_names: tuple[str, ...]
    level_map: "OrderedDict[str, tuple[str, ...]]"
    converged: bool


# ---------------------------------------------------------------------------
# Long-format -> design matrix
# ---------------------------------------------------------------------------
def _attribute_columns(df: pd.DataFrame) -> "OrderedDict[str, None]":
    """Discover attribute columns (suffix ``=level``) preserving insertion order."""
    columns: "OrderedDict[str, None]" = OrderedDict()
    for column in df.columns:
        if isinstance(column, str) and column.endswith("=level"):
            attribute = column[: -len("=level")]
            columns[attribute] = None
    return columns


def _level_map_from_frame(
    df: pd.DataFrame, attribute_levels: Mapping[str, Sequence[str]] | None
) -> "OrderedDict[str, tuple[str, ...]]":
    """Resolve attribute->levels: explicit mapping wins, else infer from frame."""
    if attribute_levels is not None:
        return OrderedDict(
            (attribute, tuple(levels)) for attribute, levels in attribute_levels.items()
        )

    discovered: "OrderedDict[str, list[str]]" = OrderedDict()
    for attribute in _attribute_columns(df):
        column = f"{attribute}=level"
        seen: list[str] = []
        for raw in df[column].tolist():
            if isinstance(raw, float) and np.isnan(raw):
                continue
            text = str(raw)
            if not text:
                continue
            if text not in seen:
                seen.append(text)
        if seen:
            discovered[attribute] = seen
    return OrderedDict((attribute, tuple(levels)) for attribute, levels in discovered.items())


def _profile_from_row(row: pd.Series, attributes: Sequence[str]) -> Profile:
    """Build a :class:`Profile` from a long-format row."""
    levels: list[tuple[str, str]] = []
    for attribute in attributes:
        value = row.get(f"{attribute}=level", "")
        if isinstance(value, float) and np.isnan(value):
            value = ""
        levels.append((attribute, str(value)))
    return Profile(levels=tuple(levels))


def build_tournament_matrix(
    df: pd.DataFrame,
    attribute_levels: Mapping[str, Sequence[str]] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], "OrderedDict[str, tuple[str, ...]]"]:
    """Project Tournament rows into ``(X, y, group_ids, columns, level_map)``.

    ``group_ids`` is a 1-D array assigning each row to its task (so the
    log-likelihood softmax can be applied per task).
    """
    tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT].copy()
    if tournament.empty:
        raise ValueError("no Tournament rows in the response frame")
    level_map = _level_map_from_frame(tournament, attribute_levels)
    if not level_map:
        raise ValueError("could not infer any attribute->levels mapping from the frame")

    attributes = list(level_map.keys())
    tournament = tournament.sort_values(
        by=[RESPONDENT_COL, TASK_ID_COL, ALTERNATIVE_INDEX_COL]
    ).reset_index(drop=True)

    profiles = [_profile_from_row(row, attributes) for _, row in tournament.iterrows()]
    matrix, columns, _ = effects_code(profiles, level_map)
    y = tournament[CHOSEN_COL].to_numpy(dtype=float)
    group_keys = tournament[[RESPONDENT_COL, TASK_ID_COL]].astype(str).agg("|".join, axis=1)
    _, group_ids = np.unique(group_keys.to_numpy(), return_inverse=True)
    return matrix, y, group_ids, columns, level_map


# ---------------------------------------------------------------------------
# §3 — MNL log-likelihood + fit
# ---------------------------------------------------------------------------
def mnl_log_likelihood(
    beta: np.ndarray,
    X: np.ndarray,
    y: np.ndarray,
    group_ids: np.ndarray,
) -> float:
    """Multinomial-logit log-likelihood (sum over tasks).

    ``X`` is the per-alternative design matrix (shape ``(n_alts_total,
    n_features)``); ``y`` is the chosen indicator (0/1, exactly one per
    task); ``group_ids`` assigns each alternative to its task.

    For numerical stability we subtract the per-group max from the
    linear predictor before exponentiating.
    """
    utilities = X @ beta
    # Per-group max for stability.
    group_max = np.full(group_ids.max() + 1, -np.inf)
    np.maximum.at(group_max, group_ids, utilities)
    stable = utilities - group_max[group_ids]
    exp_utils = np.exp(stable)
    group_sum = np.zeros_like(group_max)
    np.add.at(group_sum, group_ids, exp_utils)
    log_norm = np.log(group_sum)
    log_probs = stable - log_norm[group_ids]
    return float(np.sum(y * log_probs))


def _neg_log_likelihood_and_gradient(
    beta: np.ndarray,
    X: np.ndarray,
    y: np.ndarray,
    group_ids: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Return ``(-LL, -∇LL)``; the analytic gradient is ``Xᵀ (y - p)``."""
    utilities = X @ beta
    n_groups = int(group_ids.max()) + 1
    group_max = np.full(n_groups, -np.inf)
    np.maximum.at(group_max, group_ids, utilities)
    stable = utilities - group_max[group_ids]
    exp_utils = np.exp(stable)
    group_sum = np.zeros(n_groups)
    np.add.at(group_sum, group_ids, exp_utils)
    probs = exp_utils / group_sum[group_ids]
    ll = float(np.sum(y * (stable - np.log(group_sum)[group_ids])))
    gradient = X.T @ (y - probs)
    return -ll, -gradient


def fit_mnl(
    X: np.ndarray,
    y: np.ndarray,
    group_ids: np.ndarray,
    *,
    column_names: Sequence[str] | None = None,
    level_map: "OrderedDict[str, tuple[str, ...]] | None" = None,
    max_iter: int = 500,
) -> MNLFit:
    """Maximum-likelihood MNL fit via L-BFGS-B."""
    from scipy.optimize import minimize  # lazy import keeps the module light

    if X.size == 0:
        raise ValueError("design matrix is empty — no Tournament data to fit")
    if y.shape[0] != X.shape[0] or group_ids.shape[0] != X.shape[0]:
        raise ValueError("X, y and group_ids must share the first dimension")

    beta0 = np.zeros(X.shape[1])
    result = minimize(
        _neg_log_likelihood_and_gradient,
        beta0,
        args=(X, y, group_ids),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": max_iter},
    )

    n_tasks = int(np.unique(group_ids).size)
    columns = tuple(column_names) if column_names is not None else tuple()
    final_map: "OrderedDict[str, tuple[str, ...]]" = OrderedDict(level_map or {})
    return MNLFit(
        beta=np.asarray(result.x, dtype=float),
        log_likelihood=float(-result.fun),
        n_tasks=n_tasks,
        column_names=columns,
        level_map=final_map,
        converged=bool(result.success),
    )


# ---------------------------------------------------------------------------
# Root Likelihood (RLH) — per-respondent inattention score
# ---------------------------------------------------------------------------
def compute_rlh(log_likelihood: float, n_tasks: int) -> float:
    """``RLH = exp(LL / n_tasks)`` — geometric mean of choice probabilities."""
    if n_tasks <= 0:
        raise ValueError(f"n_tasks must be positive (got {n_tasks})")
    return float(np.exp(log_likelihood / n_tasks))


def per_respondent_rlh(
    df: pd.DataFrame,
    fit: MNLFit,
    *,
    attribute_levels: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Per-respondent RLH using the population beta as the scoring rule."""
    tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT]
    if tournament.empty:
        return pd.DataFrame(columns=[RESPONDENT_COL, "rlh", "n_tasks"])

    rows: list[dict[str, object]] = []
    level_map = fit.level_map or _level_map_from_frame(tournament, attribute_levels)
    for respondent, block in tournament.groupby(RESPONDENT_COL, sort=False):
        X, y, groups, _, _ = build_tournament_matrix(
            block.assign(**{STAGE_COL: STAGE_TOURNAMENT}), level_map
        )
        ll = mnl_log_likelihood(fit.beta, X, y, groups)
        n_tasks = int(np.unique(groups).size)
        rows.append(
            {RESPONDENT_COL: respondent, "rlh": compute_rlh(ll, n_tasks), "n_tasks": n_tasks}
        )
    return pd.DataFrame(rows)


def filter_by_rlh(rlh_frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Drop respondents whose RLH falls below ``threshold``."""
    if "rlh" not in rlh_frame.columns:
        raise ValueError("rlh_frame is missing the 'rlh' column")
    return rlh_frame[rlh_frame["rlh"] >= threshold].copy()


# ---------------------------------------------------------------------------
# Importance — Range_A / Σ Range
# ---------------------------------------------------------------------------
def beta_to_level_utilities(
    beta: np.ndarray,
    column_names: Sequence[str],
    level_map: Mapping[str, Sequence[str]],
) -> "OrderedDict[str, OrderedDict[str, float]]":
    """Reconstruct full per-level utilities from effects-coded betas.

    Surviving levels take their fitted beta; the dropped (last) level
    gets ``-Σ`` of its attribute's surviving betas.
    """
    column_lookup = {name: index for index, name in enumerate(column_names)}
    utilities: "OrderedDict[str, OrderedDict[str, float]]" = OrderedDict()
    for attribute, levels in level_map.items():
        per_level: "OrderedDict[str, float]" = OrderedDict()
        survivors_sum = 0.0
        for level in levels[:-1]:
            column = f"{attribute}__{level}"
            if column not in column_lookup:
                raise KeyError(f"missing column {column!r} in fitted matrix")
            value = float(beta[column_lookup[column]])
            per_level[level] = value
            survivors_sum += value
        per_level[levels[-1]] = -survivors_sum
        utilities[attribute] = per_level
    return utilities


def attribute_importance(
    fit: MNLFit,
) -> pd.DataFrame:
    """Compute ``absolute / relative`` importance per attribute.

    ``Range_A = max_ℓ U_ℓ - min_ℓ U_ℓ`` (full-utility scale, not the
    effects-coded β). ``relative_importance = Range_A / Σ Range``. The
    returned frame uses exactly the :data:`conjoint.io.IMPORTANCE_COLUMNS`
    column order, so :mod:`compute_distance_matrix` can ingest the
    output unchanged.
    """
    utilities = beta_to_level_utilities(fit.beta, fit.column_names, fit.level_map)
    ranges: "OrderedDict[str, float]" = OrderedDict()
    for attribute, per_level in utilities.items():
        values = list(per_level.values())
        if not values:
            ranges[attribute] = 0.0
            continue
        ranges[attribute] = float(max(values) - min(values))
    total = float(sum(ranges.values()))
    if total <= 0.0:
        raise ValueError("total attribute range is zero; cannot normalise importance")
    return pd.DataFrame(
        {
            ATTRIBUTE_COL: list(ranges.keys()),
            ABSOLUTE_IMPORTANCE_COL: list(ranges.values()),
            RELATIVE_IMPORTANCE_COL: [value / total for value in ranges.values()],
        },
        columns=list(IMPORTANCE_COLUMNS),
    )


# ---------------------------------------------------------------------------
# End-to-end convenience
# ---------------------------------------------------------------------------
def fit_from_responses(
    df: pd.DataFrame,
    attribute_levels: Mapping[str, Sequence[str]] | None = None,
) -> MNLFit:
    """One-shot: long-format frame -> MNLFit (Tournament rows only)."""
    X, y, groups, columns, level_map = build_tournament_matrix(df, attribute_levels)
    return fit_mnl(X, y, groups, column_names=columns, level_map=level_map)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_attribute_levels(path: PathLike | None) -> dict[str, list[str]] | None:
    if path is None:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("attribute_levels.json must be a JSON object")
    result: dict[str, list[str]] = {}
    for attribute, levels in raw.items():
        codes: list[str] = []
        for level in levels:
            if isinstance(level, dict) and "code" in level:
                codes.append(str(level["code"]))
            else:
                codes.append(str(level))
        if codes:
            result[str(attribute)] = codes
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the ``python -m conjoint.acbc.estimate`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m conjoint.acbc.estimate",
        description="ACBC MNL estimation (Tournament rows -> importance.csv).",
    )
    parser.add_argument(
        "--responses",
        type=Path,
        required=True,
        help="acbc_responses.csv long-format file.",
    )
    parser.add_argument(
        "--attribute-levels",
        type=Path,
        default=None,
        help="attribute_levels.json overriding the levels inferred from the frame.",
    )
    parser.add_argument(
        "--out-importance",
        type=Path,
        default=None,
        help="where to write importance.csv (columns compatible with conjoint.io).",
    )
    parser.add_argument(
        "--out-utilities",
        type=Path,
        default=None,
        help="optional per-level utilities JSON output.",
    )
    parser.add_argument(
        "--out-rlh",
        type=Path,
        default=None,
        help="optional per-respondent RLH diagnostic CSV.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    df = acbc_responses.read_acbc_responses(args.responses)
    attribute_levels = _load_attribute_levels(args.attribute_levels)
    fit = fit_from_responses(df, attribute_levels)
    importance = attribute_importance(fit)

    if args.out_importance is not None:
        write_importance(importance, args.out_importance)
        logger.info(
            "Wrote importance for %d attributes to %s",
            len(importance), args.out_importance
        )

    if args.out_utilities is not None:
        utilities = beta_to_level_utilities(fit.beta, fit.column_names, fit.level_map)
        Path(args.out_utilities).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_utilities).write_text(
            json.dumps(
                {attribute: dict(values) for attribute, values in utilities.items()},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        logger.info("Wrote per-level utilities to %s", args.out_utilities)

    if args.out_rlh is not None:
        rlh_frame = per_respondent_rlh(df, fit)
        rlh_frame.to_csv(args.out_rlh, index=False)
        logger.info(
            "Wrote per-respondent RLH for %d respondents to %s",
            len(rlh_frame), args.out_rlh
        )

    for _, row in importance.iterrows():
        print(
            f"  {row[ATTRIBUTE_COL]:<14s} "
            f"RI={row[RELATIVE_IMPORTANCE_COL] * 100:6.2f}%  "
            f"AI={row[ABSOLUTE_IMPORTANCE_COL]:.4f}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
