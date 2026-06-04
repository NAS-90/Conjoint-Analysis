"""Long-format ACBC response schema + assemble/validate helpers.

``acbc_responses.csv`` is the on-disk artifact that captures everything a
respondent did across BYO / Screener / Tournament. It is a *long* format:
one row per (respondent, stage, task, alternative).

Schema (column order is part of the contract):

* ``respondent`` — respondent identifier (string or int).
* ``stage`` — one of :data:`STAGE_BYO`, :data:`STAGE_SCREENER`,
  :data:`STAGE_TOURNAMENT`.
* ``task_id`` — 1-based id of the task within its stage.
* ``alternative_index`` — 0-based position inside the task.
* ``chosen`` — ``1`` if this alternative was chosen, ``0`` otherwise.
  For BYO this is "is this the preferred level"; for the Screener it is
  the Yes/No flag; for the Tournament it is the picked profile.
* ``<attribute>=<level_code>`` — one column per Part B-1 attribute,
  encoding the alternative's profile. For BYO, only the attribute being
  asked about has a value (other attributes are blank).

This module is intentionally storage-agnostic; it just turns Python
records into a ``pandas.DataFrame`` with stable columns + light
validation. Estimation (:mod:`conjoint.acbc.estimate`) consumes the
frame; downstream tools like :mod:`compute_distance_matrix` continue to
read ``importance.csv`` produced by estimate.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import pandas as pd

from conjoint.acbc.design import Profile
from conjoint.acbc.tournament import Task

#: Column names shared across BYO / Screener / Tournament rows.
RESPONDENT_COL = "respondent"
STAGE_COL = "stage"
TASK_ID_COL = "task_id"
ALTERNATIVE_INDEX_COL = "alternative_index"
CHOSEN_COL = "chosen"
FIXED_COLUMNS: tuple[str, ...] = (
    RESPONDENT_COL,
    STAGE_COL,
    TASK_ID_COL,
    ALTERNATIVE_INDEX_COL,
    CHOSEN_COL,
)

#: Stage labels stored in :data:`STAGE_COL`.
STAGE_BYO = "byo"
STAGE_SCREENER = "screener"
STAGE_TOURNAMENT = "tournament"
KNOWN_STAGES: frozenset[str] = frozenset({STAGE_BYO, STAGE_SCREENER, STAGE_TOURNAMENT})


# ---------------------------------------------------------------------------
# Input records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TournamentResponse:
    """One Tournament task answered by one respondent."""

    respondent: object
    task: Task
    chosen_index: int

    def __post_init__(self) -> None:
        if not 0 <= self.chosen_index < len(self.task.alternatives):
            raise ValueError(
                f"chosen_index {self.chosen_index} out of range for task "
                f"{self.task.task_id} ({len(self.task.alternatives)} alternatives)"
            )


@dataclass(frozen=True)
class ScreenerResponse:
    """One Screener profile + Yes/No answer."""

    respondent: object
    task_id: int
    profile: Profile
    accepted: bool


@dataclass(frozen=True)
class ByoResponse:
    """One BYO attribute + chosen level."""

    respondent: object
    task_id: int
    attribute: str
    chosen_level: str


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _attribute_columns(attribute_levels: Mapping[str, Sequence[str]]) -> list[str]:
    """``attribute=level`` columns we emit (one per Part B-1 attribute)."""
    return [f"{attribute}=level" for attribute in attribute_levels]


def _row_skeleton(
    respondent: object,
    stage: str,
    task_id: int,
    alternative_index: int,
    chosen: int,
    attribute_columns: Sequence[str],
) -> dict[str, object]:
    """Empty row with fixed columns filled and attribute columns blank."""
    row: dict[str, object] = OrderedDict()
    row[RESPONDENT_COL] = respondent
    row[STAGE_COL] = stage
    row[TASK_ID_COL] = task_id
    row[ALTERNATIVE_INDEX_COL] = alternative_index
    row[CHOSEN_COL] = chosen
    for column in attribute_columns:
        row[column] = ""
    return row


def _profile_to_row(
    profile: Profile, attribute_columns: Sequence[str]
) -> dict[str, str]:
    """Map profile attribute->level into the attribute columns."""
    cells: dict[str, str] = {}
    profile_levels = profile.as_dict
    for column in attribute_columns:
        attribute = column[: -len("=level")] if column.endswith("=level") else column
        cells[column] = profile_levels.get(attribute, "")
    return cells


def assemble_tournament_responses(
    responses: Iterable[TournamentResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for the Tournament stage only."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        for index, profile in enumerate(response.task.alternatives):
            row = _row_skeleton(
                respondent=response.respondent,
                stage=STAGE_TOURNAMENT,
                task_id=response.task.task_id,
                alternative_index=index,
                chosen=1 if index == response.chosen_index else 0,
                attribute_columns=attribute_cols,
            )
            row.update(_profile_to_row(profile, attribute_cols))
            rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def assemble_screener_responses(
    responses: Iterable[ScreenerResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for the Screener stage (one alt per row)."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        row = _row_skeleton(
            respondent=response.respondent,
            stage=STAGE_SCREENER,
            task_id=response.task_id,
            alternative_index=0,
            chosen=1 if response.accepted else 0,
            attribute_columns=attribute_cols,
        )
        row.update(_profile_to_row(response.profile, attribute_cols))
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def assemble_byo_responses(
    responses: Iterable[ByoResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for the BYO stage (one preferred level per row)."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        row = _row_skeleton(
            respondent=response.respondent,
            stage=STAGE_BYO,
            task_id=response.task_id,
            alternative_index=0,
            chosen=1,
            attribute_columns=attribute_cols,
        )
        target_col = f"{response.attribute}=level"
        if target_col not in attribute_cols:
            raise ValueError(
                f"BYO response references unknown attribute {response.attribute!r}"
            )
        row[target_col] = response.chosen_level
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def concat_responses(*frames: pd.DataFrame) -> pd.DataFrame:
    """Stack stage frames preserving their shared column order."""
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        if not frames:
            return pd.DataFrame()
        return frames[0].copy()
    return pd.concat(non_empty, ignore_index=True)


# ---------------------------------------------------------------------------
# Validation + IO
# ---------------------------------------------------------------------------
def validate_acbc_responses(
    df: pd.DataFrame,
    attribute_levels: Mapping[str, Sequence[str]],
) -> list[str]:
    """Return a list of problems (empty when the frame is valid)."""
    problems: list[str] = []
    for column in FIXED_COLUMNS:
        if column not in df.columns:
            problems.append(f"missing required column '{column}'")
    if problems:
        return problems

    expected_attr_cols = _attribute_columns(attribute_levels)
    for column in expected_attr_cols:
        if column not in df.columns:
            problems.append(f"missing attribute column '{column}'")

    if STAGE_COL in df.columns:
        bad_stages = sorted(set(df[STAGE_COL]) - KNOWN_STAGES - {""})
        if bad_stages:
            problems.append(
                f"unknown stage values: {bad_stages!r} (expected one of "
                f"{sorted(KNOWN_STAGES)})"
            )

    if CHOSEN_COL in df.columns:
        bad_chosen = df[CHOSEN_COL].dropna().tolist()
        for value in bad_chosen:
            if value not in (0, 1, "0", "1", True, False):
                problems.append(f"chosen must be 0/1 (got {value!r})")
                break

    # Each Tournament task must record exactly one chosen alternative.
    if STAGE_COL in df.columns and CHOSEN_COL in df.columns:
        tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT]
        if not tournament.empty:
            grouped = tournament.groupby([RESPONDENT_COL, TASK_ID_COL])[CHOSEN_COL].sum()
            multi = grouped[grouped != 1]
            for (respondent, task_id), total in multi.items():
                problems.append(
                    f"tournament task (respondent={respondent}, task={task_id}) has "
                    f"{int(total)} chosen alternative(s), expected exactly 1"
                )
    return problems


def write_acbc_responses(df: pd.DataFrame, path: str | "pd.io.parsers.PathLike[str]") -> None:
    """Write ``acbc_responses.csv`` (UTF-8, no index)."""
    df.to_csv(path, index=False)


def read_acbc_responses(path: str | "pd.io.parsers.PathLike[str]") -> pd.DataFrame:
    """Read ``acbc_responses.csv`` produced by :func:`write_acbc_responses`."""
    return pd.read_csv(path)
