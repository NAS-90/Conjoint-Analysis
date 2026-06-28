"""Long-format survey response schema + assemble/validate helpers.

``acbc_responses.csv`` is the on-disk artifact that captures everything a
respondent did across the linear questionnaire — Part A background, B1
ratings, B2 must-have/unacceptable, B4 choice (Tournament), B5 calibration
and Part C WTP — plus the legacy BYO / Screener stages. It is a *long*
format: one row per (respondent, stage, task, alternative).

Schema (column order is part of the contract):

* ``respondent`` — respondent identifier (string or int).
* ``stage`` — one of :data:`KNOWN_STAGES` (``background`` / ``rating`` /
  ``musthave`` / ``tournament`` / ``calibration`` / ``wtp`` and the legacy
  ``byo`` / ``screener``).
* ``task_id`` — 1-based id of the task within its stage.
* ``alternative_index`` — 0-based position inside the task.
* ``chosen`` — ``1`` if this alternative was chosen, ``0`` otherwise (the
  Tournament picked profile / Screener Yes-No / BYO preferred level). Blank
  for value-style stages that record an answer in ``response_value`` instead.
* ``item`` — generic per-row key: an attribute name (rating / must-have) or a
  background / WTP question id. Blank for pure profile rows.
* ``response_value`` — generic answer: a 1..5 rating, a ``must_have`` /
  ``unacceptable`` verdict, a 0..5 calibration probability, a WTP amount band
  or a background answer. Blank where ``chosen`` carries the signal.
* ``<attribute>=<level_code>`` — one column per Part B-1 attribute,
  encoding the alternative's profile. For per-attribute value rows (BYO /
  rating / must-have) only the asked attribute has a value.

This module is intentionally storage-agnostic; it just turns Python
records into a ``pandas.DataFrame`` with stable columns + light
validation. Estimation (:mod:`conjoint.acbc.estimate`) consumes the
frame; downstream tools like :mod:`compute_distance_matrix` continue to
read ``importance.csv`` produced by estimate.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from conjoint.acbc.design import Profile
from conjoint.acbc.tournament import Task

#: Column names shared across every survey stage.
RESPONDENT_COL = "respondent"
STAGE_COL = "stage"
TASK_ID_COL = "task_id"
ALTERNATIVE_INDEX_COL = "alternative_index"
CHOSEN_COL = "chosen"
#: Generic key for non-profile rows — an attribute name (ratings / must-have)
#: or a background / WTP question id. Blank for pure profile rows.
ITEM_COL = "item"
#: Generic answer slot for value-style sections — a 1..5 rating, a
#: ``must_have``/``unacceptable`` verdict, a 0..5 calibration probability or a
#: WTP amount band. Blank where :data:`CHOSEN_COL` already carries the signal.
RESPONSE_VALUE_COL = "response_value"
FIXED_COLUMNS: tuple[str, ...] = (
    RESPONDENT_COL,
    STAGE_COL,
    TASK_ID_COL,
    ALTERNATIVE_INDEX_COL,
    CHOSEN_COL,
    ITEM_COL,
    RESPONSE_VALUE_COL,
)

#: Stage labels stored in :data:`STAGE_COL`.
STAGE_BYO = "byo"
STAGE_SCREENER = "screener"
STAGE_TOURNAMENT = "tournament"
#: Part A/B/C stages added for the linear questionnaire (collect-into-CSV).
STAGE_BACKGROUND = "background"  # Part A profiling
STAGE_RATING = "rating"  # B1 per-level desirability
STAGE_MUSTHAVE = "musthave"  # B2 must-have / unacceptable level constraints
STAGE_CALIBRATION = "calibration"  # B5 purchase-probability calibration
STAGE_WTP = "wtp"  # Part C willingness-to-pay
KNOWN_STAGES: frozenset[str] = frozenset(
    {
        STAGE_BYO,
        STAGE_SCREENER,
        STAGE_TOURNAMENT,
        STAGE_BACKGROUND,
        STAGE_RATING,
        STAGE_MUSTHAVE,
        STAGE_CALIBRATION,
        STAGE_WTP,
    }
)


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


@dataclass(frozen=True)
class BackgroundResponse:
    """One Part A profiling question + the respondent's answer."""

    respondent: object
    task_id: int
    question_id: str
    answer: str


@dataclass(frozen=True)
class RatingResponse:
    """One B1 desirability rating for a single (attribute, level)."""

    respondent: object
    task_id: int
    attribute: str
    level: str
    rating: int


@dataclass(frozen=True)
class ConstraintResponse:
    """One B2 must-have / unacceptable verdict on a single (attribute, level)."""

    respondent: object
    task_id: int
    attribute: str
    level: str
    verdict: str  # "must_have" | "unacceptable"

    def __post_init__(self) -> None:
        if self.verdict not in {"must_have", "unacceptable"}:
            raise ValueError(
                f"verdict must be 'must_have' or 'unacceptable' (got {self.verdict!r})"
            )


@dataclass(frozen=True)
class CalibrationResponse:
    """One B5 calibration concept + 0..5 purchase probability."""

    respondent: object
    task_id: int
    profile: Profile
    probability: int

    def __post_init__(self) -> None:
        if not 0 <= int(self.probability) <= 5:
            raise ValueError(
                f"probability must be in 0..5 (got {self.probability!r})"
            )


@dataclass(frozen=True)
class WtpResponse:
    """One Part C willingness-to-pay answer (amount band) for a feature."""

    respondent: object
    task_id: int
    feature_id: str
    answer: str


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
    chosen: object,
    attribute_columns: Sequence[str],
    *,
    item: str = "",
    response_value: object = "",
) -> dict[str, object]:
    """Empty row with fixed columns filled and attribute columns blank.

    ``chosen`` may be ``""`` for value-style stages (rating / must-have /
    calibration / background / WTP) where no choice was made; ``item`` and
    ``response_value`` carry the per-row key and answer for those stages.
    """
    row: dict[str, object] = OrderedDict()
    row[RESPONDENT_COL] = respondent
    row[STAGE_COL] = stage
    row[TASK_ID_COL] = task_id
    row[ALTERNATIVE_INDEX_COL] = alternative_index
    row[CHOSEN_COL] = chosen
    row[ITEM_COL] = item
    row[RESPONSE_VALUE_COL] = response_value
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


def assemble_background_responses(
    responses: Iterable[BackgroundResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for Part A (one profiling question per row)."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        rows.append(
            _row_skeleton(
                respondent=response.respondent,
                stage=STAGE_BACKGROUND,
                task_id=response.task_id,
                alternative_index=0,
                chosen="",
                attribute_columns=attribute_cols,
                item=response.question_id,
                response_value=response.answer,
            )
        )
    return pd.DataFrame(rows, columns=columns)


def assemble_rating_responses(
    responses: Iterable[RatingResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for B1 (one (attribute, level) rating per row)."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        target_col = f"{response.attribute}=level"
        if target_col not in attribute_cols:
            raise ValueError(
                f"rating response references unknown attribute {response.attribute!r}"
            )
        row = _row_skeleton(
            respondent=response.respondent,
            stage=STAGE_RATING,
            task_id=response.task_id,
            alternative_index=0,
            chosen="",
            attribute_columns=attribute_cols,
            item=response.attribute,
            response_value=response.rating,
        )
        row[target_col] = response.level
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def assemble_musthave_responses(
    responses: Iterable[ConstraintResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for B2 (one flagged (attribute, level) per row)."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        target_col = f"{response.attribute}=level"
        if target_col not in attribute_cols:
            raise ValueError(
                f"constraint response references unknown attribute {response.attribute!r}"
            )
        row = _row_skeleton(
            respondent=response.respondent,
            stage=STAGE_MUSTHAVE,
            task_id=response.task_id,
            alternative_index=0,
            chosen="",
            attribute_columns=attribute_cols,
            item=response.attribute,
            response_value=response.verdict,
        )
        row[target_col] = response.level
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def assemble_calibration_responses(
    responses: Iterable[CalibrationResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for B5 (one full concept + probability per row)."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        row = _row_skeleton(
            respondent=response.respondent,
            stage=STAGE_CALIBRATION,
            task_id=response.task_id,
            alternative_index=0,
            chosen="",
            attribute_columns=attribute_cols,
            response_value=int(response.probability),
        )
        row.update(_profile_to_row(response.profile, attribute_cols))
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def assemble_wtp_responses(
    responses: Iterable[WtpResponse],
    attribute_levels: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Long-format frame for Part C (one feature + amount band per row)."""
    columns = list(FIXED_COLUMNS) + _attribute_columns(attribute_levels)
    attribute_cols = _attribute_columns(attribute_levels)
    rows: list[dict[str, object]] = []
    for response in responses:
        rows.append(
            _row_skeleton(
                respondent=response.respondent,
                stage=STAGE_WTP,
                task_id=response.task_id,
                alternative_index=0,
                chosen="",
                attribute_columns=attribute_cols,
                item=response.feature_id,
                response_value=response.answer,
            )
        )
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
        # Value-style stages (rating / must-have / calibration / background /
        # WTP) leave ``chosen`` blank — only the choice stages use 0/1.
        bad_chosen = df[CHOSEN_COL].dropna().tolist()
        for value in bad_chosen:
            if value not in (0, 1, "0", "1", True, False, ""):
                problems.append(f"chosen must be 0/1 or blank (got {value!r})")
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


#: Filename prefix the survey app's "Send my responses" button uses.
RESPONSES_FILE_PREFIX = "responses_"


def respondent_id_from_filename(name: str | Path) -> str:
    """Derive a respondent id from one questionnaire's filename.

    Each fielded questionnaire is a single CSV (``responses_<id>.csv`` from the
    survey app). The id is the file stem with a leading ``responses_`` dropped,
    so ``responses_P017.csv`` → ``P017`` and ``john.csv`` → ``john``.
    """
    stem = Path(str(name)).stem
    if stem.startswith(RESPONSES_FILE_PREFIX):
        stem = stem[len(RESPONSES_FILE_PREFIX):]
    return stem or "respondent"


def read_respondent_csv(source: object, name: str | Path | None = None) -> pd.DataFrame:
    """Read ONE questionnaire CSV, stamping ``respondent`` from its filename.

    ``source`` may be a path or a file-like (e.g. a Streamlit upload); pass
    ``name`` when ``source`` has no usable path of its own (an upload's
    ``.name``). The single returned frame has its :data:`RESPONDENT_COL` set to
    :func:`respondent_id_from_filename`, enforcing **one file == one respondent**.
    """
    frame = read_acbc_responses(source)
    label = name if name is not None else source
    return frame.assign(**{RESPONDENT_COL: respondent_id_from_filename(label)})


def read_responses_dir(folder: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """Read a folder of per-respondent questionnaire CSVs into one long frame.

    The collect-the-survey counterpart to :func:`read_acbc_responses`: each
    ``*.csv`` in ``folder`` is one completed questionnaire, read via
    :func:`read_respondent_csv` so ids stay unique and traceable across files no
    matter what each person typed in the survey.

    Returns the concatenated long-format frame plus the sorted list of files
    read. Raises if ``folder`` is not a directory or holds no ``*.csv``.
    """
    directory = Path(folder)
    if not directory.is_dir():
        raise NotADirectoryError(f"not a folder: {directory}")
    files = sorted(directory.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no questionnaire CSVs (*.csv) found in {directory}")
    frames = [read_respondent_csv(path, path.name) for path in files]
    return concat_responses(*frames), [str(path) for path in files]
