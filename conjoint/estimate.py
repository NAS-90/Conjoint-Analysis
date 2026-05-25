"""Module 3 — Conjoint computation (OLS per respondent + aggregation).

Implements :mod:`algorithm_spec.md` §3 (OLS dummy regression, CVA convention)
and §4 (aggregation across respondents). The on-disk contract is owned by
:mod:`conjoint.io`; this module only reads/writes through it.

Two estimation paths are exposed via the CLI:

* ``--responses responses.csv``  — Part B-1 ratings (1..5) -> OLS -> utilities
  -> aggregation. This is the full Module 3 pipeline.
* ``--utilities utilities.csv``  — pre-computed per-respondent part-worths
  (e.g. the N=381 fixture) -> aggregation only. The §4 path is the one
  validated against the published reference numbers.

OLS recipe (§3), applied per respondent and **per attribute independently**:

1. Build a design matrix ``X`` with one column per level, one row per rated
   level, then drop the first level of each attribute to avoid collinearity.
2. Build ``y`` from the 1..5 ratings, optionally recoded to -2..+2 (centered).
3. Solve ``β, α = OLS(X, y)`` with an explicit intercept.
4. Reconstruct the dropped levels at coefficient ``0`` and add ``α / K`` to
   every level (``K`` = number of attributes), then zero-center each attribute.
   Zero-centering is the CVA presentation convention used by the reference
   ``AllHP`` table — every attribute's level utilities sum to zero, which makes
   two-level attributes symmetric (``basic = -premium``).
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from conjoint.io import (
    ABSOLUTE_IMPORTANCE_COL,
    ATTRIBUTE_COL,
    IMPORTANCE_COLUMNS,
    PathLike,
    RELATIVE_IMPORTANCE_COL,
    RESPONDENT_COL,
    read_responses,
    read_utilities,
    response_column,
    split_response_column,
    write_importance,
    write_utilities,
)

# Public type aliases ---------------------------------------------------------
AttributeLevels = Mapping[str, Sequence[str]]
PartWorths = "OrderedDict[str, OrderedDict[str, float]]"

#: Lowest / highest points on the Part B-1 rating scale.
RATING_MIN = 1
RATING_MAX = 5
#: Midpoint subtracted when ``recode`` is enabled: 1..5 -> -2..+2.
RATING_RECODE_MIDPOINT = (RATING_MIN + RATING_MAX) / 2.0


# ---------------------------------------------------------------------------
# Attribute / level grouping helpers
# ---------------------------------------------------------------------------
def levels_from_attribute_levels(attribute_levels: object) -> "OrderedDict[str, list[str]]":
    """Normalise an attribute->levels mapping into ``{attr: [level_code, ...]}``.

    Accepts either the rich ``attribute_levels.json`` shape
    (``{attr: [{"code": ..., "label": ...}, ...]}``) or a plain
    ``{attr: [code, ...]}`` mapping. Order is preserved.
    """
    if not isinstance(attribute_levels, Mapping):
        raise ValueError("attribute_levels must be a mapping of attribute -> levels")
    grouping: "OrderedDict[str, list[str]]" = OrderedDict()
    for attribute, levels in attribute_levels.items():
        codes: list[str] = []
        for level in levels:
            if isinstance(level, Mapping):
                code = level.get("code")
            else:
                code = level
            if not code:
                raise ValueError(f"attribute {attribute!r} has an empty level code")
            codes.append(str(code))
        if not codes:
            raise ValueError(f"attribute {attribute!r} has no levels")
        grouping[attribute] = codes
    return grouping


def grouping_from_columns(columns: Sequence[str]) -> "OrderedDict[str, list[str]]":
    """Derive ``{attr: [level_code, ...]}`` from utility/response column names.

    Uses :func:`conjoint.io.split_response_column` so the parsing rules stay in
    one place. ``respondent`` (and any other column without the separator) is
    ignored. First-seen order is preserved for both attributes and levels.
    """
    grouping: "OrderedDict[str, list[str]]" = OrderedDict()
    for column in columns:
        if column == RESPONDENT_COL:
            continue
        try:
            attribute, level_code = split_response_column(column)
        except ValueError:
            continue
        grouping.setdefault(attribute, [])
        if level_code not in grouping[attribute]:
            grouping[attribute].append(level_code)
    if not grouping:
        raise ValueError("no '{attribute}__{level}' columns found to group")
    return grouping


def _resolve_grouping(
    attribute_levels: Optional[object],
    columns: Sequence[str],
) -> "OrderedDict[str, list[str]]":
    """Use an explicit mapping when given, else infer it from the columns."""
    if attribute_levels is not None:
        return levels_from_attribute_levels(attribute_levels)
    return grouping_from_columns(columns)


# ---------------------------------------------------------------------------
# §3 — OLS per respondent
# ---------------------------------------------------------------------------
def estimate_part_worths(
    ratings: Mapping[str, float],
    grouping: AttributeLevels,
    *,
    recode: bool = True,
) -> "OrderedDict[str, OrderedDict[str, float]]":
    """Estimate one respondent's part-worth utilities from Part B-1 ratings.

    ``ratings`` maps ``{attribute}__{level}`` -> rating (1..5). ``grouping`` maps
    each attribute to its ordered level codes. Returns
    ``{attribute: {level_code: part_worth}}`` with each attribute zero-centered.

    Each attribute is regressed independently (own intercept), the first level
    is dropped to avoid collinearity, the dropped level is reconstructed at 0,
    ``intercept / K`` is added to every level, and finally the attribute is
    zero-centered (the CVA presentation convention; see module docstring).
    """
    num_attributes = len(grouping)
    if num_attributes == 0:
        raise ValueError("grouping must contain at least one attribute")

    part_worths: "OrderedDict[str, OrderedDict[str, float]]" = OrderedDict()
    for attribute, level_codes in grouping.items():
        coefficients, intercept = _ols_attribute(
            attribute, level_codes, ratings, recode=recode
        )
        recentered = [coef + intercept / num_attributes for coef in coefficients]
        centered = _zero_center(recentered)
        part_worths[attribute] = OrderedDict(zip(level_codes, centered))
    return part_worths


def _ols_attribute(
    attribute: str,
    level_codes: Sequence[str],
    ratings: Mapping[str, float],
    *,
    recode: bool,
) -> tuple[list[float], float]:
    """Solve OLS for a single attribute; return (level coefficients, intercept).

    The design matrix has an intercept column plus one dummy per surviving level
    (the first level is dropped). The returned coefficient list is aligned with
    ``level_codes`` and starts the dropped level at ``0.0``.
    """
    rows: list[list[float]] = []
    targets: list[float] = []
    num_levels = len(level_codes)
    for index, code in enumerate(level_codes):
        column = response_column(attribute, code)
        if column not in ratings:
            raise KeyError(
                f"missing rating for column {column!r} (attribute {attribute!r})"
            )
        rating = ratings[column]
        if pd.isna(rating):
            continue  # least-squares fills in unrated levels from the rest
        # intercept + dummies for surviving levels (drop index 0)
        row = [1.0] + [1.0 if j == index else 0.0 for j in range(1, num_levels)]
        rows.append(row)
        targets.append(_recode_rating(float(rating), recode=recode))

    if not rows:
        raise ValueError(f"attribute {attribute!r} has no ratings to estimate")

    design = np.asarray(rows, dtype=float)
    response = np.asarray(targets, dtype=float)
    solution, *_ = np.linalg.lstsq(design, response, rcond=None)
    intercept = float(solution[0])
    # solution[1:] are the surviving-level coefficients; dropped level starts at 0.
    coefficients = [0.0] + [float(value) for value in solution[1:]]
    return coefficients, intercept


def _recode_rating(rating: float, *, recode: bool) -> float:
    """Map a 1..5 rating to -2..+2 (recode) or pass it through unchanged.

    Zero-centering each attribute downstream makes the additive constant
    irrelevant, so ``recode`` never changes the final part-worths; it is exposed
    for transparency and tested explicitly.
    """
    return rating - RATING_RECODE_MIDPOINT if recode else rating


def _zero_center(values: Sequence[float]) -> list[float]:
    """Subtract the mean so the values sum to zero (CVA presentation)."""
    mean = float(np.mean(values))
    return [value - mean for value in values]


def estimate_utilities(
    responses_df: pd.DataFrame,
    attribute_levels: Optional[object] = None,
    *,
    recode: bool = True,
) -> pd.DataFrame:
    """Run §3 OLS over every respondent; return a tidy ``utilities`` frame.

    The output has ``respondent`` plus one ``{attribute}__{level}`` part-worth
    column per level, in the order implied by ``attribute_levels`` (or by the
    response columns when no mapping is supplied).
    """
    if RESPONDENT_COL not in responses_df.columns:
        raise ValueError(f"responses frame is missing '{RESPONDENT_COL}'")
    grouping = _resolve_grouping(attribute_levels, list(responses_df.columns))
    ordered_columns = [
        response_column(attribute, code)
        for attribute, codes in grouping.items()
        for code in codes
    ]

    records: list[dict[str, float]] = []
    for _, row in responses_df.iterrows():
        ratings = {column: row[column] for column in ordered_columns if column in row}
        part_worths = estimate_part_worths(ratings, grouping, recode=recode)
        record: dict[str, float] = {RESPONDENT_COL: row[RESPONDENT_COL]}
        for attribute, levels in part_worths.items():
            for code, value in levels.items():
                record[response_column(attribute, code)] = value
        records.append(record)

    columns = [RESPONDENT_COL, *ordered_columns]
    return pd.DataFrame.from_records(records, columns=columns)


# ---------------------------------------------------------------------------
# §4 — Aggregation across respondents
# ---------------------------------------------------------------------------
def aggregate_importance(
    utilities_df: pd.DataFrame,
    attribute_levels: Optional[object] = None,
) -> pd.DataFrame:
    """Compute absolute / relative importance per attribute (§4).

    For each respondent ``r`` and attribute ``a``:
    ``d_{a,r} = |max_ℓ u| + |min_ℓ u|``; ``AI_a = mean_r d_{a,r}``;
    ``RI_a = AI_a / Σ_a AI_a``. Returns a frame with exactly the columns
    ``attribute, absolute_importance, relative_importance``.
    """
    grouping = _resolve_grouping(attribute_levels, list(utilities_df.columns))
    absolute: "OrderedDict[str, float]" = OrderedDict()
    for attribute, level_codes in grouping.items():
        columns = [response_column(attribute, code) for code in level_codes]
        _require_utility_columns(utilities_df, columns, attribute)
        block = utilities_df[columns]
        spread = block.max(axis=1).abs() + block.min(axis=1).abs()
        absolute[attribute] = float(spread.mean())

    total = float(sum(absolute.values()))
    if total <= 0.0:
        raise ValueError("total absolute importance is zero; cannot normalise")

    frame = pd.DataFrame(
        {
            ATTRIBUTE_COL: list(absolute.keys()),
            ABSOLUTE_IMPORTANCE_COL: list(absolute.values()),
            RELATIVE_IMPORTANCE_COL: [value / total for value in absolute.values()],
        }
    )
    return frame.loc[:, list(IMPORTANCE_COLUMNS)]


def population_utilities(
    utilities_df: pd.DataFrame,
    attribute_levels: Optional[object] = None,
) -> "OrderedDict[str, OrderedDict[str, float]]":
    """Mean part-worth per level across respondents (§4 population utilities).

    Returns ``{attribute: {level_code: mean_r u}}`` preserving attribute and
    level order.
    """
    grouping = _resolve_grouping(attribute_levels, list(utilities_df.columns))
    result: "OrderedDict[str, OrderedDict[str, float]]" = OrderedDict()
    for attribute, level_codes in grouping.items():
        levels: "OrderedDict[str, float]" = OrderedDict()
        for code in level_codes:
            column = response_column(attribute, code)
            _require_utility_columns(utilities_df, [column], attribute)
            levels[code] = float(utilities_df[column].mean())
        result[attribute] = levels
    return result


def _require_utility_columns(
    df: pd.DataFrame, columns: Sequence[str], attribute: str
) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(
            f"utilities frame is missing column(s) for attribute {attribute!r}: "
            f"{', '.join(missing)}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_attribute_levels(path: Optional[PathLike]) -> Optional[object]:
    if path is None:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_population_json(
    utilities: "OrderedDict[str, OrderedDict[str, float]]", path: PathLike
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialisable = {attr: dict(levels) for attr, levels in utilities.items()}
    target.write_text(
        json.dumps(serialisable, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the ``python -m conjoint.estimate`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m conjoint.estimate",
        description="Conjoint OLS estimation (§3) and aggregation (§4).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--responses",
        type=Path,
        help="responses.csv with 1..5 Part B-1 ratings (runs OLS then aggregates).",
    )
    source.add_argument(
        "--utilities",
        type=Path,
        help="pre-computed utilities.csv (skips OLS; aggregates directly).",
    )
    parser.add_argument(
        "--attribute-levels",
        type=Path,
        default=None,
        help="attribute_levels.json mapping attribute -> ordered levels.",
    )
    parser.add_argument(
        "--out-utilities",
        type=Path,
        default=None,
        help="where to write per-respondent utilities (responses path only).",
    )
    parser.add_argument(
        "--out-importance",
        type=Path,
        default=None,
        help="where to write aggregated importance.csv.",
    )
    parser.add_argument(
        "--out-population",
        type=Path,
        default=None,
        help="optional population_utilities.json output.",
    )
    parser.add_argument(
        "--no-recode",
        action="store_true",
        help="keep raw 1..5 ratings instead of recoding to -2..+2.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    attribute_levels = _load_attribute_levels(args.attribute_levels)

    if args.responses is not None:
        responses = read_responses(args.responses)
        utilities = estimate_utilities(
            responses, attribute_levels, recode=not args.no_recode
        )
        if args.out_utilities is not None:
            write_utilities(utilities, args.out_utilities)
            print(f"Wrote utilities for {len(utilities)} respondents to {args.out_utilities}")
    else:
        utilities = read_utilities(args.utilities)
        print(f"Loaded utilities for {len(utilities)} respondents from {args.utilities}")

    importance = aggregate_importance(utilities, attribute_levels)
    if args.out_importance is not None:
        write_importance(importance, args.out_importance)
        print(f"Wrote importance for {len(importance)} attributes to {args.out_importance}")

    if args.out_population is not None:
        population = population_utilities(utilities, attribute_levels)
        _write_population_json(population, args.out_population)
        print(f"Wrote population utilities to {args.out_population}")

    for _, row in importance.iterrows():
        print(
            f"  {row[ATTRIBUTE_COL]:<14s} "
            f"RI={row[RELATIVE_IMPORTANCE_COL] * 100:6.2f}%  "
            f"AI={row[ABSOLUTE_IMPORTANCE_COL]:.4f}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
