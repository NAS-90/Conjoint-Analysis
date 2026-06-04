"""ACBC model diagnostics (§9.10 #10 + §8 "model diagnostics" / sanity checks).

Three families of pre-simulation checks the reference material requires before
trusting estimated utilities:

* **Holdout hit rate** — fit on a random subset of Tournament tasks, then count
  how often the model's argmax prediction matches the actual choice on the
  *held-out* tasks. Compared against the per-task random baseline ``mean(1/J)``.
* **Monotonicity / outlier utilities** — for an attribute with an inherent
  order (price, tier, horsepower), check the level utilities move in the
  expected direction. "The most expensive level has the highest utility" is the
  canonical red flag (§8).
* **Dominant-attribute** — guard against any single attribute unrealistically
  dominating the model (relative importance above a threshold).

These read fitted results; they never mutate inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from conjoint.acbc.estimate import (
    _level_map_from_frame,
    build_tournament_matrix,
    fit_from_responses,
)
from conjoint.acbc.responses import (
    RESPONDENT_COL,
    STAGE_COL,
    STAGE_TOURNAMENT,
    TASK_ID_COL,
)
from conjoint.io import ATTRIBUTE_COL, RELATIVE_IMPORTANCE_COL

#: ``{attribute: {level_code: utility}}``.
LevelUtilities = Mapping[str, Mapping[str, float]]

_TOL = 1e-9


# ---------------------------------------------------------------------------
# Holdout hit rate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HoldoutResult:
    """Argmax prediction accuracy on held-out Tournament tasks."""

    hit_rate: float
    n_holdout_tasks: int
    n_correct: int
    random_baseline: float

    @property
    def beats_random(self) -> bool:
        """Whether the model predicts better than chance on the holdout."""
        return self.hit_rate > self.random_baseline


def predict_hit_rate(
    df: pd.DataFrame,
    beta: np.ndarray,
    *,
    level_map: Mapping[str, Sequence[str]],
) -> HoldoutResult:
    """Argmax hit rate of a fixed ``beta`` over the Tournament tasks in ``df``.

    ``beta`` must be aligned with the columns that
    :func:`conjoint.acbc.estimate.build_tournament_matrix` produces from
    ``level_map`` (pass the same ``level_map`` used to fit it).
    """
    X, y, group_ids, _, _ = build_tournament_matrix(df, level_map)
    utilities = X @ np.asarray(beta, dtype=float)

    n_correct = 0
    n_tasks = 0
    baseline_sum = 0.0
    for group in np.unique(group_ids):
        mask = group_ids == group
        util_g = utilities[mask]
        y_g = y[mask]
        n_tasks += 1
        baseline_sum += 1.0 / util_g.shape[0]
        if y_g[int(np.argmax(util_g))] == 1:
            n_correct += 1

    hit_rate = n_correct / n_tasks if n_tasks else 0.0
    baseline = baseline_sum / n_tasks if n_tasks else 0.0
    return HoldoutResult(
        hit_rate=float(hit_rate),
        n_holdout_tasks=int(n_tasks),
        n_correct=int(n_correct),
        random_baseline=float(baseline),
    )


def _task_keys(tournament: pd.DataFrame) -> pd.Series:
    """``respondent|task_id`` key per row (groups alternatives into tasks)."""
    return tournament[[RESPONDENT_COL, TASK_ID_COL]].astype(str).agg("|".join, axis=1)


def holdout_hit_rate(
    df: pd.DataFrame,
    *,
    holdout_fraction: float = 0.25,
    seed: int | None = 0,
    attribute_levels: Mapping[str, Sequence[str]] | None = None,
) -> HoldoutResult:
    """Split Tournament tasks → fit MNL on train → hit rate on the holdout.

    Tasks (not rows) are split so no alternative leaks between train and
    holdout. The training fit uses the *full*-data level map so every level has
    a column even if the split leaves it out of training.
    """
    if not 0.0 < holdout_fraction < 1.0:
        raise ValueError("holdout_fraction must be in (0, 1)")
    tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT]
    if tournament.empty:
        raise ValueError("no Tournament rows to evaluate")

    level_map = _level_map_from_frame(tournament, attribute_levels)
    keys = _task_keys(tournament)
    unique_keys = list(dict.fromkeys(keys.tolist()))
    if len(unique_keys) < 2:
        raise ValueError("need at least 2 Tournament tasks to hold one out")

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(unique_keys))
    n_holdout = min(len(unique_keys) - 1, max(1, int(round(len(unique_keys) * holdout_fraction))))
    holdout_keys = {unique_keys[i] for i in order[:n_holdout]}
    is_holdout = keys.isin(holdout_keys).to_numpy()

    train = tournament[~is_holdout].assign(**{STAGE_COL: STAGE_TOURNAMENT})
    holdout = tournament[is_holdout].assign(**{STAGE_COL: STAGE_TOURNAMENT})

    fit = fit_from_responses(train, level_map)
    return predict_hit_rate(holdout, fit.beta, level_map=level_map)


# ---------------------------------------------------------------------------
# Monotonicity / outlier utilities
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MonotonicityResult:
    """Whether an ordered attribute's utilities move in the expected direction."""

    attribute: str
    ordered_levels: tuple[str, ...]
    utilities: tuple[float, ...]
    expect_decreasing: bool
    monotonic: bool
    violations: tuple[tuple[str, str], ...]


def check_monotonicity(
    level_utilities: LevelUtilities,
    attribute: str,
    ordered_levels: Sequence[str],
    *,
    expect_decreasing: bool = True,
) -> MonotonicityResult:
    """Check ``attribute``'s utilities follow ``ordered_levels`` monotonically.

    ``ordered_levels`` lists the levels in their natural increasing order (e.g.
    price low→high). With ``expect_decreasing=True`` (the price default) the
    utilities should be non-increasing along that order; each adjacent pair that
    rises instead is recorded as a violation — Sawtooth's "outlier utility"
    (higher price → higher utility).
    """
    per_level = level_utilities.get(attribute)
    if per_level is None:
        raise KeyError(f"attribute {attribute!r} not in level_utilities")
    if len(ordered_levels) < 2:
        raise ValueError("ordered_levels needs at least 2 levels to be monotone")

    utilities: list[float] = []
    for level in ordered_levels:
        if level not in per_level:
            raise KeyError(f"level {level!r} not found for attribute {attribute!r}")
        utilities.append(float(per_level[level]))

    violations: list[tuple[str, str]] = []
    for (lo_level, lo_util), (hi_level, hi_util) in zip(
        zip(ordered_levels, utilities), zip(ordered_levels[1:], utilities[1:])
    ):
        if expect_decreasing and hi_util > lo_util + _TOL:
            violations.append((lo_level, hi_level))
        elif not expect_decreasing and hi_util < lo_util - _TOL:
            violations.append((lo_level, hi_level))

    return MonotonicityResult(
        attribute=attribute,
        ordered_levels=tuple(ordered_levels),
        utilities=tuple(utilities),
        expect_decreasing=expect_decreasing,
        monotonic=not violations,
        violations=tuple(violations),
    )


# ---------------------------------------------------------------------------
# Dominant-attribute guard
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DominanceResult:
    """The single most important attribute, and whether it over-dominates."""

    attribute: str
    relative_importance: float
    threshold: float
    dominates: bool


def dominant_attribute(
    importance: pd.DataFrame,
    *,
    threshold: float = 0.5,
) -> DominanceResult:
    """Flag when one attribute's relative importance exceeds ``threshold``.

    ``importance`` is the frame produced by
    :func:`conjoint.acbc.estimate.attribute_importance` (columns
    :data:`conjoint.io.ATTRIBUTE_COL` / :data:`RELATIVE_IMPORTANCE_COL`).
    """
    if importance.empty:
        raise ValueError("importance frame is empty")
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    top_index = importance[RELATIVE_IMPORTANCE_COL].idxmax()
    row = importance.loc[top_index]
    relative = float(row[RELATIVE_IMPORTANCE_COL])
    return DominanceResult(
        attribute=str(row[ATTRIBUTE_COL]),
        relative_importance=relative,
        threshold=float(threshold),
        dominates=bool(relative > threshold),
    )
