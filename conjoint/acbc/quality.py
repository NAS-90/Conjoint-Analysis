"""ACBC data-quality screening (§8 "How to Clean and Analyze … Raw Data").

Conjoint cleaning is different from ordinary survey cleaning: the signal lives
in the *pattern* of choices, not in individual answers. This module screens the
long-format response frame (:mod:`conjoint.acbc.responses`) for the four issues
the reference material calls out, emitting one flag row per respondent:

* **straightlining / non-differentiation** — the respondent always picks the
  same Tournament ``alternative_index`` (position), i.e. they never actually
  discriminate between concepts.
* **inconsistent / illogical choices** — the respondent picked a *strictly
  dominated* concept: another alternative in the same task was at least as good
  on every attribute and strictly better on one (e.g. "always the most
  expensive"). Requires per-level utilities to judge dominance direction.
* **incomplete interviews** — fewer Tournament tasks than a full interview, or
  a task with no recorded choice at all.
* **speeding** *(optional)* — bottom-quantile total interview duration. Only
  evaluated when a duration column is present; otherwise the flag is ``<NA>``
  and :func:`quality_summary` notes that timing was not collected.

The screen is read-only and never mutates the input frame. Flagging here does
not drop anyone — pair it with :func:`conjoint.acbc.estimate.filter_by_rlh`
(RLH-based filtering, §9.6) to decide who to exclude.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from conjoint.acbc.responses import (
    ALTERNATIVE_INDEX_COL,
    CHOSEN_COL,
    RESPONDENT_COL,
    STAGE_COL,
    STAGE_TOURNAMENT,
    TASK_ID_COL,
)

#: ``{attribute: {level_code: utility}}`` — typically from
#: :func:`conjoint.acbc.estimate.beta_to_level_utilities`.
LevelUtilities = Mapping[str, Mapping[str, float]]

# Output column names (part of the contract consumed by the dashboard/report).
N_TASKS_COL = "n_tournament_tasks"
STRAIGHTLINING_COL = "straightlining"
INCONSISTENT_COL = "inconsistent_choices"
INCONSISTENT_FRACTION_COL = "inconsistent_fraction"
INCOMPLETE_COL = "incomplete"
SPEEDING_COL = "speeding"
N_FLAGS_COL = "n_flags"
FLAGGED_COL = "flagged"

FLAG_COLUMNS: tuple[str, ...] = (
    RESPONDENT_COL,
    N_TASKS_COL,
    STRAIGHTLINING_COL,
    INCONSISTENT_COL,
    INCONSISTENT_FRACTION_COL,
    INCOMPLETE_COL,
    SPEEDING_COL,
    N_FLAGS_COL,
    FLAGGED_COL,
)

#: Numerical tolerance when comparing level utilities for dominance.
_DOMINANCE_TOL = 1e-9


@dataclass(frozen=True)
class QualityThresholds:
    """Tunable cut-offs for the quality screen.

    * ``min_tournament_tasks`` — a respondent needs at least this many Tournament
      tasks before "always the same position" counts as straightlining (one or
      two tasks can coincide by chance).
    * ``speeding_quantile`` — respondents in the bottom this-fraction of total
      duration are flagged as speeding.
    * ``max_inconsistent_fraction`` — flag once the share of dominance-bearing
      tasks on which a *strictly dominated* concept was chosen exceeds this.
      Default ``0.5`` flags only sustained illogical choosers ("always the most
      expensive"). It is deliberately not ``0``: choice data is noisy, so an
      attentive respondent occasionally picks a dominated alt by chance — the
      discriminating signal is the *rate*, not a single slip. Lower it for
      stricter screening (and expect more borderline flags).
    """

    min_tournament_tasks: int = 3
    speeding_quantile: float = 0.05
    max_inconsistent_fraction: float = 0.5

    def __post_init__(self) -> None:
        if self.min_tournament_tasks < 1:
            raise ValueError("min_tournament_tasks must be >= 1")
        if not 0.0 <= self.speeding_quantile < 1.0:
            raise ValueError("speeding_quantile must be in [0, 1)")
        if not 0.0 <= self.max_inconsistent_fraction <= 1.0:
            raise ValueError("max_inconsistent_fraction must be in [0, 1]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _chosen_mask(series: pd.Series) -> pd.Series:
    """Coerce a ``chosen`` column (0/1, "0"/"1", True/False) to a boolean mask."""
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int) == 1


def _tournament(df: pd.DataFrame) -> pd.DataFrame:
    """Tournament rows only (empty frame if the stage column is absent)."""
    if STAGE_COL not in df.columns:
        return df.iloc[0:0]
    return df[df[STAGE_COL] == STAGE_TOURNAMENT]


def _expected_task_count(counts: Sequence[int]) -> int:
    """Full-interview length = the most common per-respondent task count.

    The mode is robust to a stray over-long export; ties resolve to the larger
    count so a genuinely longer interview is treated as complete.
    """
    if not counts:
        return 0
    frequency = Counter(counts)
    top = max(frequency.values())
    return max(count for count, freq in frequency.items() if freq == top)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def _straightlining_flags(
    tournament: pd.DataFrame, min_tasks: int
) -> dict[object, bool]:
    """Respondents who always pick the same ``alternative_index`` position."""
    flags: dict[object, bool] = {}
    for respondent, block in tournament.groupby(RESPONDENT_COL, sort=False):
        chosen = block[_chosen_mask(block[CHOSEN_COL])]
        # One chosen alternative per task → its position.
        positions = (
            chosen.groupby(TASK_ID_COL)[ALTERNATIVE_INDEX_COL]
            .first()
            .to_numpy()
        )
        n_tasks = positions.shape[0]
        flags[respondent] = bool(
            n_tasks >= min_tasks and np.unique(positions).size == 1
        )
    return flags


def _incomplete_flags(
    tournament: pd.DataFrame, expected_tasks: int | None
) -> dict[object, bool]:
    """Respondents missing tasks, or with an unanswered (no-choice) task."""
    per_respondent_tasks: dict[object, int] = {}
    unanswered: dict[object, bool] = {}
    for respondent, block in tournament.groupby(RESPONDENT_COL, sort=False):
        task_groups = block.groupby(TASK_ID_COL)
        per_respondent_tasks[respondent] = task_groups.ngroups
        unanswered[respondent] = bool(
            (task_groups[CHOSEN_COL].apply(lambda s: int(_chosen_mask(s).sum())) == 0).any()
        )

    target = (
        expected_tasks
        if expected_tasks is not None
        else _expected_task_count(list(per_respondent_tasks.values()))
    )
    return {
        respondent: bool(per_respondent_tasks[respondent] < target or unanswered[respondent])
        for respondent in per_respondent_tasks
    }


def _alternative_utility_vector(
    row: pd.Series, attributes: Sequence[str], level_utilities: LevelUtilities
) -> np.ndarray | None:
    """Per-attribute utility vector for one alternative, or ``None`` if a level
    is unknown to ``level_utilities`` (the task is then unassessable)."""
    vector = np.empty(len(attributes), dtype=float)
    for index, attribute in enumerate(attributes):
        level = row.get(f"{attribute}=level", "")
        if isinstance(level, float) and np.isnan(level):
            level = ""
        per_level = level_utilities.get(attribute, {})
        if level not in per_level:
            return None
        vector[index] = float(per_level[level])
    return vector


def _dominated(target: np.ndarray, others: Sequence[np.ndarray]) -> bool:
    """Is ``target`` strictly dominated by any alternative in ``others``?

    ``other`` dominates ``target`` when it is ≥ on every attribute and strictly
    greater on at least one.
    """
    for other in others:
        if np.all(other >= target - _DOMINANCE_TOL) and np.any(
            other > target + _DOMINANCE_TOL
        ):
            return True
    return False


def _inconsistent_fractions(
    tournament: pd.DataFrame, level_utilities: LevelUtilities
) -> dict[object, float]:
    """Per-respondent fraction of tasks where a *dominated* concept was chosen."""
    attributes = list(level_utilities.keys())
    fractions: dict[object, float] = {}
    for respondent, block in tournament.groupby(RESPONDENT_COL, sort=False):
        assessable = 0
        dominated_picks = 0
        for _task_id, task in block.groupby(TASK_ID_COL):
            vectors: list[np.ndarray] = []
            chosen_idx: int | None = None
            chosen_mask = _chosen_mask(task[CHOSEN_COL]).to_numpy()
            unassessable = False
            for position, (_, alt_row) in enumerate(task.iterrows()):
                vector = _alternative_utility_vector(alt_row, attributes, level_utilities)
                if vector is None:
                    unassessable = True
                    break
                vectors.append(vector)
                if chosen_mask[position]:
                    chosen_idx = position
            if unassessable or chosen_idx is None or len(vectors) < 2:
                continue
            assessable += 1
            others = [v for i, v in enumerate(vectors) if i != chosen_idx]
            if _dominated(vectors[chosen_idx], others):
                dominated_picks += 1
        fractions[respondent] = dominated_picks / assessable if assessable else 0.0
    return fractions


def _speeding_flags(
    df: pd.DataFrame, duration_col: str, quantile: float
) -> dict[object, bool]:
    """Flag respondents whose total duration is in the bottom ``quantile``."""
    durations = (
        df.assign(_dur=pd.to_numeric(df[duration_col], errors="coerce"))
        .groupby(RESPONDENT_COL, sort=False)["_dur"]
        .sum(min_count=1)
    )
    valid = durations.dropna()
    if valid.empty:
        return {respondent: False for respondent in durations.index}
    cutoff = float(np.quantile(valid.to_numpy(), quantile))
    return {
        respondent: bool(pd.notna(total) and total <= cutoff)
        for respondent, total in durations.items()
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def screen_quality(
    df: pd.DataFrame,
    *,
    level_utilities: LevelUtilities | None = None,
    expected_tasks: int | None = None,
    duration_col: str | None = None,
    thresholds: QualityThresholds = QualityThresholds(),
) -> pd.DataFrame:
    """Per-respondent §8 quality flags.

    ``level_utilities`` enables the dominated-choice (inconsistency) check; when
    omitted that column is ``False`` for everyone. ``duration_col`` enables the
    speeding check; when omitted (or absent from ``df``) the speeding column is
    ``<NA>``. Returns one row per respondent with :data:`FLAG_COLUMNS`.
    """
    tournament = _tournament(df)
    if tournament.empty:
        return pd.DataFrame(columns=list(FLAG_COLUMNS))

    respondents = list(dict.fromkeys(tournament[RESPONDENT_COL].tolist()))
    task_counts = (
        tournament.groupby(RESPONDENT_COL, sort=False)[TASK_ID_COL].nunique().to_dict()
    )

    straightlining = _straightlining_flags(tournament, thresholds.min_tournament_tasks)
    incomplete = _incomplete_flags(tournament, expected_tasks)
    inconsistent_fraction = (
        _inconsistent_fractions(tournament, level_utilities)
        if level_utilities
        else {respondent: 0.0 for respondent in respondents}
    )

    speeding_checked = duration_col is not None and duration_col in df.columns
    speeding = (
        _speeding_flags(df, duration_col, thresholds.speeding_quantile)
        if speeding_checked
        else {}
    )

    rows: list[dict[str, object]] = []
    for respondent in respondents:
        is_straight = straightlining.get(respondent, False)
        is_incomplete = incomplete.get(respondent, False)
        fraction = inconsistent_fraction.get(respondent, 0.0)
        is_inconsistent = fraction > thresholds.max_inconsistent_fraction
        is_speeding = speeding.get(respondent, False) if speeding_checked else pd.NA

        hard_flags = [is_straight, is_inconsistent, is_incomplete]
        if speeding_checked:
            hard_flags.append(bool(is_speeding))
        n_flags = int(sum(bool(flag) for flag in hard_flags))

        rows.append(
            {
                RESPONDENT_COL: respondent,
                N_TASKS_COL: int(task_counts.get(respondent, 0)),
                STRAIGHTLINING_COL: bool(is_straight),
                INCONSISTENT_COL: bool(is_inconsistent),
                INCONSISTENT_FRACTION_COL: float(fraction),
                INCOMPLETE_COL: bool(is_incomplete),
                SPEEDING_COL: is_speeding,
                N_FLAGS_COL: n_flags,
                FLAGGED_COL: bool(n_flags > 0),
            }
        )
    return pd.DataFrame(rows, columns=list(FLAG_COLUMNS))


def quality_summary(flags: pd.DataFrame) -> dict[str, object]:
    """Aggregate counts over a :func:`screen_quality` frame.

    ``speeding_checked`` is ``False`` when the duration column was absent, so the
    report can state plainly that interview timing was not collected rather than
    implying everyone passed the speeding check.
    """
    n = int(len(flags))
    if n == 0:
        return {
            "n_respondents": 0,
            "n_flagged": 0,
            STRAIGHTLINING_COL: 0,
            INCONSISTENT_COL: 0,
            INCOMPLETE_COL: 0,
            SPEEDING_COL: 0,
            "speeding_checked": False,
        }
    speeding_checked = bool(SPEEDING_COL in flags and flags[SPEEDING_COL].notna().any())
    return {
        "n_respondents": n,
        "n_flagged": int(flags[FLAGGED_COL].sum()),
        STRAIGHTLINING_COL: int(flags[STRAIGHTLINING_COL].sum()),
        INCONSISTENT_COL: int(flags[INCONSISTENT_COL].sum()),
        INCOMPLETE_COL: int(flags[INCOMPLETE_COL].sum()),
        SPEEDING_COL: int(flags[SPEEDING_COL].fillna(False).sum()) if speeding_checked else 0,
        "speeding_checked": speeding_checked,
    }
