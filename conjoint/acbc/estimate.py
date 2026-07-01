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
# §9.8 — utility rescaling (readability transforms; the raw path is untouched)
# ---------------------------------------------------------------------------
#: Method names accepted by :func:`rescale_utilities`.
RESCALE_ZERO_CENTERED = "zero_centered"
RESCALE_ZERO_CENTERED_DIFFS = "zero_centered_diffs"
RESCALE_NORMALIZED_RANGES = "normalized_ranges"


def _attribute_range(per_level: Mapping[str, float]) -> float:
    """``max - min`` of an attribute's level utilities (``0`` when empty)."""
    values = list(per_level.values())
    if not values:
        return 0.0
    return float(max(values) - min(values))


def zero_center_utilities(
    utilities: Mapping[str, Mapping[str, float]],
) -> "OrderedDict[str, OrderedDict[str, float]]":
    """Subtract each attribute's mean so its level utilities sum to zero.

    Effects-coded β already satisfy ``Σ level utilities = 0`` per attribute
    (§9.5), but this makes the constraint explicit for utilities that arrive
    from elsewhere. Returns a fresh structure — the input is never mutated.
    """
    rescaled: "OrderedDict[str, OrderedDict[str, float]]" = OrderedDict()
    for attribute, per_level in utilities.items():
        values = list(per_level.values())
        mean = sum(values) / len(values) if values else 0.0
        rescaled[attribute] = OrderedDict(
            (level, float(value) - mean) for level, value in per_level.items()
        )
    return rescaled


def rescale_zero_centered_diffs(
    utilities: Mapping[str, Mapping[str, float]],
    *,
    target_range: float = 100.0,
) -> "OrderedDict[str, OrderedDict[str, float]]":
    """Sawtooth "zero-centered diffs": mean attribute range → ``target_range``.

    Zero-centres within each attribute, then multiplies *every* utility by the
    single constant ``target_range · A / Σ_a range_a`` (``A`` = attribute
    count). The average best–worst spread across attributes then equals
    ``target_range`` while *relative importance is preserved* (one global
    factor). This is the canonical readable scale Sawtooth reports.
    """
    centred = zero_center_utilities(utilities)
    ranges = [_attribute_range(per_level) for per_level in centred.values()]
    total_range = float(sum(ranges))
    n_attr = len(centred)
    if total_range <= 0.0 or n_attr == 0:
        return centred
    factor = target_range * n_attr / total_range
    return OrderedDict(
        (
            attribute,
            OrderedDict((level, value * factor) for level, value in per_level.items()),
        )
        for attribute, per_level in centred.items()
    )


def normalize_utility_ranges(
    utilities: Mapping[str, Mapping[str, float]],
    *,
    scale: float = 100.0,
) -> "OrderedDict[str, OrderedDict[str, float]]":
    """Per-attribute ``0..scale`` normalisation ("utility ranges normalized").

    Each attribute is rescaled *independently* so its worst level maps to ``0``
    and its best to ``scale`` (flat attributes map to all-zero). This answers
    "within this attribute, how much better is the best level" but discards
    cross-attribute importance, so it is a readability view — **not** a
    simulation input. Use :func:`rescale_zero_centered_diffs` for simulation.
    """
    rescaled: "OrderedDict[str, OrderedDict[str, float]]" = OrderedDict()
    for attribute, per_level in utilities.items():
        values = [float(value) for value in per_level.values()]
        if not values:
            rescaled[attribute] = OrderedDict()
            continue
        low, high = min(values), max(values)
        span = high - low
        if span <= 0.0:
            rescaled[attribute] = OrderedDict((level, 0.0) for level in per_level)
        else:
            rescaled[attribute] = OrderedDict(
                (level, (float(value) - low) / span * scale)
                for level, value in per_level.items()
            )
    return rescaled


def rescale_utilities(
    utilities: Mapping[str, Mapping[str, float]],
    *,
    method: str = RESCALE_ZERO_CENTERED_DIFFS,
    **kwargs: float,
) -> "OrderedDict[str, OrderedDict[str, float]]":
    """Dispatch a §9.8 readability rescaling over a ``{attr: {level: u}}`` map.

    ``method`` is one of :data:`RESCALE_ZERO_CENTERED_DIFFS` (default),
    :data:`RESCALE_NORMALIZED_RANGES`, or :data:`RESCALE_ZERO_CENTERED`.
    Extra keyword arguments (``target_range`` / ``scale``) flow to the chosen
    transform. The input mapping is never mutated.
    """
    if method == RESCALE_ZERO_CENTERED_DIFFS:
        return rescale_zero_centered_diffs(utilities, **kwargs)
    if method == RESCALE_NORMALIZED_RANGES:
        return normalize_utility_ranges(utilities, **kwargs)
    if method == RESCALE_ZERO_CENTERED:
        if kwargs:
            raise ValueError(f"{RESCALE_ZERO_CENTERED!r} takes no extra arguments")
        return zero_center_utilities(utilities)
    raise ValueError(
        f"unknown rescaling method {method!r}; expected one of "
        f"{(RESCALE_ZERO_CENTERED_DIFFS, RESCALE_NORMALIZED_RANGES, RESCALE_ZERO_CENTERED)}"
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
# Hierarchical Bayes — per-respondent betas via Metropolis-within-Gibbs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HBFit:
    """Result of a Hierarchical-Bayes fit (per-respondent + population)."""

    respondent_ids: tuple[object, ...]
    beta_means: np.ndarray             # (n_respondents, n_features)
    population_mean: np.ndarray        # (n_features,)
    population_cov: np.ndarray         # (n_features, n_features)
    rhat: np.ndarray                   # (n_features,) Gelman-Rubin convergence
    column_names: tuple[str, ...]
    level_map: "OrderedDict[str, tuple[str, ...]]"


def _respondent_blocks(
    df: pd.DataFrame, level_map: "OrderedDict[str, tuple[str, ...]]"
) -> list[tuple[object, np.ndarray, np.ndarray, np.ndarray]]:
    """Per-respondent ``(respondent_id, X, y, group_ids)`` blocks."""
    blocks: list[tuple[object, np.ndarray, np.ndarray, np.ndarray]] = []
    tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT]
    for respondent, sub in tournament.groupby(RESPONDENT_COL, sort=False):
        X, y, groups, _, _ = build_tournament_matrix(
            sub.assign(**{STAGE_COL: STAGE_TOURNAMENT}), level_map
        )
        blocks.append((respondent, X, y, groups))
    return blocks


def _safe_cholesky(matrix: np.ndarray) -> np.ndarray:
    """Cholesky factor with a small jitter fallback for proposal covariance."""
    eye = np.eye(matrix.shape[0])
    jitter = 1e-8
    for _ in range(6):
        try:
            return np.linalg.cholesky(matrix + jitter * eye)
        except np.linalg.LinAlgError:
            jitter *= 10.0
    diagonal = np.maximum(np.diag(matrix), jitter)
    return np.diag(np.sqrt(diagonal))


def _propose_beta(
    current: np.ndarray, X: np.ndarray, y: np.ndarray, groups: np.ndarray,
    population_mean: np.ndarray, population_precision: np.ndarray,
    proposal_chol: np.ndarray, step_scale: float, rng: np.random.Generator,
) -> tuple[np.ndarray, bool]:
    """One Metropolis-Hastings step for one respondent's β.

    Random-walk proposal shaped by the current population covariance; target is
    the MNL likelihood times a multivariate-normal prior at ``population_mean``.
    Returns the next β and whether the proposal was accepted so the caller can
    tune ``step_scale`` during burn-in.
    """
    proposal = current + step_scale * (proposal_chol @ rng.standard_normal(current.shape[0]))

    def log_target(beta: np.ndarray) -> float:
        ll = mnl_log_likelihood(beta, X, y, groups)
        diff = beta - population_mean
        prior = -0.5 * float(diff @ population_precision @ diff)
        return ll + prior

    log_ratio = log_target(proposal) - log_target(current)
    if np.log(rng.uniform()) < log_ratio:
        return proposal, True
    return current, False


def fit_hb(
    df: pd.DataFrame,
    *,
    attribute_levels: Mapping[str, Sequence[str]] | None = None,
    n_iter: int = 10000,
    burn_in: int = 1000,
    thinning: int = 10,
    n_chains: int = 2,
    step_scale: float = 0.3,
    prior_cov_scale: float = 4.0,
    seed: int | None = None,
) -> HBFit:
    """Hierarchical-Bayes fit via Metropolis-within-Gibbs (pure numpy).

    Hierarchy:
        β_i ~ Normal(μ, Σ)              # respondent-level
        μ   ~ Normal(0, prior_cov_scale·I)   # weak prior on the mean
        Σ   ~ Inverse-Wishart(I, n_features + 2)   # weak prior on the cov

    Sampling alternates:
        1. β_i | μ, Σ, data — Metropolis step per respondent.
        2. μ    | β, Σ      — conjugate Normal update.
        3. Σ    | β, μ      — conjugate Inverse-Wishart update.

    Returns posterior-mean β per respondent + population (μ, Σ) and a
    Gelman-Rubin Rhat per feature across chains.
    """
    if n_iter <= burn_in:
        raise ValueError("n_iter must exceed burn_in")
    if thinning < 1:
        raise ValueError("thinning must be >= 1")
    if n_chains < 2:
        raise ValueError("n_chains must be >= 2 for Rhat")
    if step_scale <= 0:
        raise ValueError("step_scale must be positive")

    level_map = _level_map_from_frame(
        df[df[STAGE_COL] == STAGE_TOURNAMENT], attribute_levels
    )
    blocks = _respondent_blocks(df, level_map)
    if not blocks:
        raise ValueError("no respondent Tournament data to fit HB")

    n_resp = len(blocks)
    n_features = blocks[0][1].shape[1]
    if n_features == 0:
        raise ValueError("no features in the design matrix")
    columns = tuple(
        f"{attribute}__{code}"
        for attribute, levels in level_map.items()
        for code in levels[:-1]
    )

    chain_means: list[np.ndarray] = []  # per-chain β means after burn-in
    population_samples_all: list[np.ndarray] = []  # per-chain μ samples
    sigma_means: list[np.ndarray] = []  # per-chain mean of the Σ draws
    rng_master = np.random.default_rng(seed)

    # ---- MLE warm-start: compute population MLE once for all chains ----
    try:
        mle_result = fit_from_responses(df, attribute_levels)
        mle_beta = mle_result.beta
    except Exception:
        mle_beta = np.zeros(n_features)

    for chain in range(n_chains):
        rng = np.random.default_rng(rng_master.integers(0, 2**31 - 1))
        betas = np.tile(mle_beta, (n_resp, 1))  # start near posterior mode
        population_mean = mle_beta.copy()
        population_cov = np.eye(n_features) * prior_cov_scale
        population_precision = np.linalg.inv(population_cov)

        kept_betas: list[np.ndarray] = []  # post-burn-in β snapshots
        kept_mu: list[np.ndarray] = []
        kept_sigma: list[np.ndarray] = []  # post-burn-in Σ (Inverse-Wishart) draws
        # Keep adaptation simple: tune one chain-level proposal scale during
        # early burn-in, then freeze it before retaining posterior samples.
        chain_step_scale = float(step_scale)
        accepted_in_window = 0
        proposed_in_window = 0
        adapt_interval = 50
        adapt_until = burn_in // 2

        for step in range(n_iter):
            # Respondent βs (Metropolis).
            proposal_chol = _safe_cholesky(population_cov)
            for i, (_, X, y, groups) in enumerate(blocks):
                betas[i], accepted = _propose_beta(
                    betas[i], X, y, groups,
                    population_mean, population_precision,
                    proposal_chol, chain_step_scale, rng,
                )
                if step < adapt_until:
                    accepted_in_window += int(accepted)
                    proposed_in_window += 1

            # μ | β, Σ — conjugate Normal posterior (diagonal Σ).
            beta_mean = betas.mean(axis=0)
            prior_prec_diag = np.ones(n_features) / prior_cov_scale
            pop_prec_diag = 1.0 / np.diag(population_cov)
            post_prec_diag = prior_prec_diag + n_resp * pop_prec_diag
            post_var_diag = 1.0 / post_prec_diag
            post_mean = post_var_diag * (n_resp * pop_prec_diag * beta_mean)
            population_mean = post_mean + np.sqrt(post_var_diag) * rng.standard_normal(n_features)

            # σ²_j | β, μ — conjugate Inverse-Gamma posterior (diagonal Σ).
            # Each feature j is independent: shape = (n_resp + prior_df) / 2,
            # scale = (Σ_i (β_ij − μ_j)² + prior_scale) / 2.
            centred = betas - population_mean
            ss_per_feature = np.sum(centred ** 2, axis=0)  # (n_features,)
            ig_shape = (n_resp + 3.0) / 2.0  # prior df = 3
            ig_scale = (ss_per_feature + 1.0) / 2.0  # prior scale = 1
            # sample σ²_j ~ Inv-Gamma(shape, scale) via 1 / Gamma(shape, 1/scale)
            variances = 1.0 / rng.gamma(ig_shape, 1.0 / ig_scale)
            population_cov = np.diag(variances)
            population_precision = np.diag(1.0 / variances)

            if step < adapt_until and (step + 1) % adapt_interval == 0 and proposed_in_window:
                acceptance_rate = accepted_in_window / proposed_in_window
                if acceptance_rate < 0.05:
                    chain_step_scale *= 0.5
                elif acceptance_rate < 0.2:
                    chain_step_scale *= 0.8
                elif acceptance_rate > 0.45:
                    chain_step_scale *= 1.2
                chain_step_scale = min(max(chain_step_scale, 1e-3), 5.0)
                accepted_in_window = 0
                proposed_in_window = 0

            if step >= burn_in and (step - burn_in) % thinning == 0:
                kept_betas.append(betas.copy())
                kept_mu.append(population_mean.copy())
                kept_sigma.append(population_cov.copy())

        if not kept_betas:
            raise RuntimeError("no samples retained after burn-in / thinning")
        chain_means.append(np.mean(np.stack(kept_betas), axis=0))
        population_samples_all.append(np.stack(kept_mu))
        sigma_means.append(np.mean(np.stack(kept_sigma), axis=0))

    chain_population = np.stack([samples.mean(axis=0) for samples in population_samples_all])
    population_mean = chain_population.mean(axis=0)
    # Heterogeneity covariance Σ — the *between-respondent* covariance the
    # hierarchy actually models. We average the per-iteration Inverse-Wishart
    # draws (``_sample_inverse_wishart``) over the post-burn-in samples and
    # across chains. (The earlier implementation returned ``cov`` of the μ
    # *posterior* samples, which shrinks toward 0 as the chains converge and is
    # not the heterogeneity Σ at all.)
    population_cov = np.mean(np.stack(sigma_means), axis=0)

    rhat = _gelman_rubin(population_samples_all)

    # Per-respondent β is the chain-averaged posterior mean.
    beta_means = np.mean(np.stack(chain_means), axis=0)

    return HBFit(
        respondent_ids=tuple(rid for rid, _, _, _ in blocks),
        beta_means=beta_means,
        population_mean=population_mean,
        population_cov=population_cov,
        rhat=rhat,
        column_names=columns,
        level_map=level_map,
    )


def _sample_inverse_wishart(scatter: np.ndarray, df_iw: int, rng: np.random.Generator) -> np.ndarray:
    """Sample from an inverse-Wishart via Bartlett decomposition."""
    p = scatter.shape[0]
    L = np.linalg.cholesky(np.linalg.inv(scatter))
    A = np.zeros((p, p))
    for i in range(p):
        A[i, i] = np.sqrt(rng.chisquare(df_iw - i))
        for j in range(i):
            A[i, j] = rng.standard_normal()
    LA = L @ A
    wishart = LA @ LA.T
    return np.linalg.inv(wishart)


def _gelman_rubin(chains: list[np.ndarray]) -> np.ndarray:
    """Per-feature Gelman-Rubin Rhat across post-burn-in chain samples."""
    if len(chains) < 2:
        return np.full(chains[0].shape[1], np.nan)
    stacked = np.stack(chains)  # (n_chains, n_samples, n_features)
    n_chains, n_samples, _ = stacked.shape
    chain_mean = stacked.mean(axis=1)              # (n_chains, n_features)
    overall_mean = chain_mean.mean(axis=0)         # (n_features,)
    between = n_samples * ((chain_mean - overall_mean) ** 2).sum(axis=0) / (n_chains - 1)
    within = stacked.var(axis=1, ddof=1).mean(axis=0)
    var_hat = (n_samples - 1) / n_samples * within + between / n_samples
    rhat = np.sqrt(var_hat / np.where(within > 0, within, 1.0))
    return rhat


def hb_to_utilities(fit: HBFit) -> pd.DataFrame:
    """Reconstruct per-respondent full-level utilities from an HB fit.

    The returned frame uses the same column convention as
    :func:`conjoint.estimate.estimate_utilities`:
    ``respondent`` + one ``{attribute}__{level_code}`` column per level
    (dropped level reconstructed as ``-Σ`` surviving betas).
    """
    rows: list[dict[str, object]] = []
    for respondent_id, beta in zip(fit.respondent_ids, fit.beta_means):
        row: dict[str, object] = {RESPONDENT_COL: respondent_id}
        for attribute, levels in fit.level_map.items():
            survivors_sum = 0.0
            for level in levels[:-1]:
                column = f"{attribute}__{level}"
                idx = fit.column_names.index(column)
                value = float(beta[idx])
                row[column] = value
                survivors_sum += value
            row[f"{attribute}__{levels[-1]}"] = -survivors_sum
        rows.append(row)
    columns = [RESPONDENT_COL] + [
        f"{attribute}__{level}"
        for attribute, levels in fit.level_map.items()
        for level in levels
    ]
    return pd.DataFrame(rows, columns=columns)


def hb_attribute_importance(fit: HBFit) -> pd.DataFrame:
    """Compute attribute importance from the *population mean* of an HB fit.

    Same Range_A / Σ Range formula as :func:`attribute_importance`, but
    sourced from the HB population posterior.
    """
    mnl_proxy = MNLFit(
        beta=fit.population_mean,
        log_likelihood=0.0,
        n_tasks=0,
        column_names=fit.column_names,
        level_map=fit.level_map,
        converged=True,
    )
    return attribute_importance(mnl_proxy)


def per_respondent_rlh_hb(
    df: pd.DataFrame,
    hb_fit: HBFit,
    *,
    attribute_levels: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Per-respondent RLH scored with each respondent's *own* HB β_i.

    Sawtooth measures attention with **individual-level** utilities, not the
    population mean (which :func:`per_respondent_rlh` uses). For respondent
    ``i`` with ``T_i`` Tournament tasks::

        RLH_i = exp( LL_i(β_i) / T_i )

    where ``β_i`` is the respondent's posterior-mean utility vector from the
    HB fit. Respondents absent from ``hb_fit`` (e.g. dropped before fitting)
    are skipped. The β columns align with the fit because both this routine
    and the fit build the design matrix from ``hb_fit.level_map``.

    Returns a frame with columns ``respondent``, ``rlh``, ``n_tasks`` — the
    same schema as :func:`per_respondent_rlh`, so it feeds straight into
    :func:`filter_by_rlh`.
    """
    tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT]
    if tournament.empty:
        return pd.DataFrame(columns=[RESPONDENT_COL, "rlh", "n_tasks"])

    level_map = hb_fit.level_map or _level_map_from_frame(tournament, attribute_levels)
    beta_by_respondent = {
        respondent: beta
        for respondent, beta in zip(hb_fit.respondent_ids, hb_fit.beta_means)
    }

    rows: list[dict[str, object]] = []
    for respondent, block in tournament.groupby(RESPONDENT_COL, sort=False):
        beta_i = beta_by_respondent.get(respondent)
        if beta_i is None:
            continue
        X, y, groups, _, _ = build_tournament_matrix(
            block.assign(**{STAGE_COL: STAGE_TOURNAMENT}), level_map
        )
        ll = mnl_log_likelihood(np.asarray(beta_i, dtype=float), X, y, groups)
        n_tasks = int(np.unique(groups).size)
        rows.append(
            {RESPONDENT_COL: respondent, "rlh": compute_rlh(ll, n_tasks), "n_tasks": n_tasks}
        )
    return pd.DataFrame(rows, columns=[RESPONDENT_COL, "rlh", "n_tasks"])


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
        description="ACBC MNL/HB estimation (Tournament rows -> importance.csv).",
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
        help="optional per-level utilities JSON output (population MNL).",
    )
    parser.add_argument(
        "--out-rlh",
        type=Path,
        default=None,
        help="optional per-respondent RLH diagnostic CSV.",
    )
    parser.add_argument(
        "--hb",
        action="store_true",
        help="run Hierarchical-Bayes after the MNL fit (slower, per-respondent betas).",
    )
    parser.add_argument(
        "--hb-iter",
        type=int,
        default=2000,
        help="number of HB iterations (default 2000).",
    )
    parser.add_argument(
        "--hb-burnin",
        type=int,
        default=1000,
        help="burn-in iterations dropped before posterior summaries (default 1000).",
    )
    parser.add_argument(
        "--out-hb-utilities",
        type=Path,
        default=None,
        help="per-respondent HB utilities CSV (matches conjoint.io.utilities schema).",
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

    if args.hb:
        hb_fit = fit_hb(
            df,
            attribute_levels=attribute_levels,
            n_iter=args.hb_iter,
            burn_in=args.hb_burnin,
        )
        logger.info(
            "HB fit: %d respondents, Rhat max=%.3f", len(hb_fit.respondent_ids),
            float(np.nanmax(hb_fit.rhat)),
        )
        if args.out_hb_utilities is not None:
            hb_utilities = hb_to_utilities(hb_fit)
            from conjoint.io import write_utilities

            write_utilities(hb_utilities, args.out_hb_utilities)
            logger.info(
                "Wrote HB per-respondent utilities for %d respondents to %s",
                len(hb_utilities), args.out_hb_utilities,
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
