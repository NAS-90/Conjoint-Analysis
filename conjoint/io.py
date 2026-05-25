"""Shared I/O contract for the conjoint pipeline (Modules 1-4).

This module is the single source of truth for the on-disk artifacts exchanged
between modules:

* ``responses.csv``  — Part B-1 ratings, one row per respondent.
* ``utilities.csv``  — per-respondent part-worth utilities (Module 3 output).
* ``importance.csv`` — aggregated absolute / relative importance (Module 3).
* ``attribute_column_map.json`` — attribute -> preprocessed columns (Module 1).

Response and utility columns share the ``{attribute}__{level_code}`` naming
convention; :func:`response_column` / :func:`split_response_column` are the only
sanctioned way to build and parse them. Keep this module dependency-light:
``pandas`` and the standard library only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import pandas as pd

LEVEL_SEP = "__"
RESPONDENT_COL = "respondent"
ATTRIBUTE_COL = "attribute"
ABSOLUTE_IMPORTANCE_COL = "absolute_importance"
RELATIVE_IMPORTANCE_COL = "relative_importance"
IMPORTANCE_COLUMNS = (ATTRIBUTE_COL, ABSOLUTE_IMPORTANCE_COL, RELATIVE_IMPORTANCE_COL)

PathLike = Union[str, Path]


# ---------------------------------------------------------------------------
# Column naming helpers
# ---------------------------------------------------------------------------
def response_column(attribute: str, level_code: str) -> str:
    """Build the ``{attribute}__{level_code}`` column name for a rating/utility.

    Both parts must be non-empty and free of the ``__`` separator so the column
    round-trips through :func:`split_response_column`.
    """
    if not attribute:
        raise ValueError("attribute must be a non-empty string")
    if not level_code:
        raise ValueError("level_code must be a non-empty string")
    if LEVEL_SEP in attribute or LEVEL_SEP in level_code:
        raise ValueError(
            f"attribute and level_code must not contain '{LEVEL_SEP}': "
            f"attribute={attribute!r}, level_code={level_code!r}"
        )
    return f"{attribute}{LEVEL_SEP}{level_code}"


def split_response_column(column: str) -> tuple[str, str]:
    """Inverse of :func:`response_column`; split on the first ``__``.

    Splitting on the first separator keeps attribute names intact while allowing
    level codes that themselves contain underscores (but not ``__``).
    """
    if LEVEL_SEP not in column:
        raise ValueError(f"column {column!r} is missing the '{LEVEL_SEP}' separator")
    attribute, level_code = column.split(LEVEL_SEP, 1)
    if not attribute or not level_code:
        raise ValueError(f"column {column!r} has an empty attribute or level code")
    return attribute, level_code


# ---------------------------------------------------------------------------
# responses.csv
# ---------------------------------------------------------------------------
def read_responses(path: PathLike) -> pd.DataFrame:
    """Read ``responses.csv`` (respondent + one rating column per level)."""
    frame = _read_csv(path)
    _require_column(frame, RESPONDENT_COL, "responses")
    return frame


def write_responses(df: pd.DataFrame, path: PathLike) -> None:
    """Write ``responses.csv``; requires a ``respondent`` column."""
    _require_column(df, RESPONDENT_COL, "responses")
    _write_csv(df, path)


# ---------------------------------------------------------------------------
# utilities.csv
# ---------------------------------------------------------------------------
def read_utilities(path: PathLike) -> pd.DataFrame:
    """Read ``utilities.csv`` (respondent + one part-worth column per level)."""
    frame = _read_csv(path)
    _require_column(frame, RESPONDENT_COL, "utilities")
    return frame


def write_utilities(df: pd.DataFrame, path: PathLike) -> None:
    """Write ``utilities.csv``; requires a ``respondent`` column."""
    _require_column(df, RESPONDENT_COL, "utilities")
    _write_csv(df, path)


# ---------------------------------------------------------------------------
# importance.csv
# ---------------------------------------------------------------------------
def read_importance(path: PathLike) -> pd.DataFrame:
    """Read ``importance.csv`` with exactly the importance columns."""
    frame = _read_csv(path)
    _require_columns(frame, IMPORTANCE_COLUMNS, "importance")
    return frame


def write_importance(df: pd.DataFrame, path: PathLike) -> None:
    """Write ``importance.csv`` with columns attribute/absolute/relative."""
    _require_columns(df, IMPORTANCE_COLUMNS, "importance")
    _write_csv(df.loc[:, list(IMPORTANCE_COLUMNS)], path)


# ---------------------------------------------------------------------------
# attribute_column_map.json
# ---------------------------------------------------------------------------
def read_attribute_map(path: PathLike) -> dict[str, dict[str, object]]:
    """Read ``attribute_column_map.json`` produced by Module 1."""
    text = Path(path).read_text(encoding="utf-8")
    mapping = json.loads(text)
    if not isinstance(mapping, dict):
        raise ValueError(f"attribute map at {path} must be a JSON object")
    return mapping


def write_attribute_map(mapping: dict[str, dict[str, object]], path: PathLike) -> None:
    """Write ``attribute_column_map.json`` (pretty-printed, UTF-8)."""
    if not isinstance(mapping, dict):
        raise ValueError("attribute map must be a dict")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _read_csv(path: PathLike) -> pd.DataFrame:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Missing CSV: {target}")
    return pd.read_csv(target)


def _write_csv(df: pd.DataFrame, path: PathLike) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)


def _require_column(df: pd.DataFrame, column: str, kind: str) -> None:
    if column not in df.columns:
        raise ValueError(f"{kind} frame is missing required column '{column}'")


def _require_columns(df: pd.DataFrame, columns: tuple[str, ...], kind: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"{kind} frame is missing required column(s): {', '.join(missing)}"
        )
