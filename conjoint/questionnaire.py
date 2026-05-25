"""Module 2 — Questionnaire generator (core).

Builds a questionnaire specification from a workbook's ``Feature_data`` sheet and
emits the artifacts Module 3 consumes:

* ``questionnaire_spec.json`` — the documented question schema (see
  :class:`QuestionnaireSpec`).
* ``responses_template.csv`` — an empty ``responses.csv`` with exactly the
  columns Module 3's design matrix expects (``respondent`` + one
  ``{attribute}__{level_code}`` column per Part B-1 rating level).

The metadata is read and canonicalised by reusing :mod:`preprocessing` (its
workbook reader, :func:`preprocessing.normalize_metadata`,
:func:`preprocessing.enforce_identifier_rules`, and the
``canonical_conjoint_*`` / ``split_semicolon`` / ``derive_level_codes`` helpers)
rather than re-parsing ``Feature_data`` from scratch.

Scope (algorithm_spec.md §2, attribute_schema.md §7):

* ``B1_rating`` attributes are fully modelled — each becomes one 1..5 rating
  question ("How desirable is each level?") with its ordered levels. These are
  flagged ``status == "active"``.
* ``B2_importance`` / ``B3_pairwise`` / ``B4_calibration`` / ``C_wtp`` attributes
  still get a spec entry (with their ordered levels) but are flagged
  ``status == "optional"``; their answer logic is out of MVP scope.

All public functions are type-annotated and return new objects (no mutation of
inputs). Keep this module dependency-light: ``pandas`` + the standard library.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Union

import pandas as pd

import preprocessing as pp
from conjoint.io import RESPONDENT_COL, response_column

PathLike = Union[str, Path]

SPEC_VERSION = "0.1"

#: Part B-1 desirability rating scale (algorithm_spec.md §2).
RATING_SCALE_MIN = 1
RATING_SCALE_MAX = 5

#: Section that is fully modelled in the MVP.
ACTIVE_SECTION = "B1_rating"

STATUS_ACTIVE = "active"
STATUS_OPTIONAL = "optional"

#: Map a ``conjoint_section`` to the human-facing question-type label used in
#: the spec. ``conjoint_question_type`` is collapsed by Module 1's aliases
#: (``b2_importance`` -> ``pairwise`` etc.), so the section is the stable signal
#: for which questionnaire part an attribute belongs to.
SECTION_QUESTION_TYPE = {
    "A_general": "general",
    "B1_rating": "rating",
    "B2_importance": "importance",
    "B3_pairwise": "pairwise",
    "B4_calibration": "calibration",
    "C_wtp": "wtp",
}

#: Fallback when ``conjoint_section`` is blank: derive the label from the
#: canonical ``conjoint_question_type`` instead.
QUESTION_TYPE_LABEL = {
    "rating": "rating",
    "pairwise": "pairwise",
    "calibration": "calibration",
    "wtp": "wtp",
}


@dataclass(frozen=True)
class Level:
    """One selectable level of an attribute (one radio row in Part B-1)."""

    code: str
    label: str


@dataclass(frozen=True)
class Scale:
    """An inclusive integer rating scale."""

    min: int
    max: int


@dataclass(frozen=True)
class AttributeQuestion:
    """One questionnaire question derived from a ``conjoint_role=attribute`` row."""

    feature_name: str
    description: str
    section: str
    question_type: str
    prompt: str
    levels: tuple[Level, ...]
    status: str
    scale: Scale | None = None

    @property
    def is_active(self) -> bool:
        """True for fully-modelled Part B-1 rating questions."""
        return self.status == STATUS_ACTIVE


@dataclass(frozen=True)
class QuestionnaireSpec:
    """Top-level questionnaire specification.

    ``attributes`` preserves the workbook (display) order. ``scale`` is the
    shared Part B-1 rating scale.
    """

    attributes: tuple[AttributeQuestion, ...]
    scale: Scale = field(default_factory=lambda: Scale(RATING_SCALE_MIN, RATING_SCALE_MAX))
    version: str = SPEC_VERSION

    @property
    def active_attributes(self) -> tuple[AttributeQuestion, ...]:
        """The Part B-1 rating questions, in workbook order."""
        return tuple(attr for attr in self.attributes if attr.is_active)


# ---------------------------------------------------------------------------
# Building the spec
# ---------------------------------------------------------------------------
def _attribute_rows(meta: pd.DataFrame) -> pd.DataFrame:
    """Return the canonicalised metadata rows with ``conjoint_role=attribute``.

    Workbook order is preserved (``normalize_metadata`` resets the index to the
    sheet order and ``enforce_identifier_rules`` keeps it).
    """
    return meta[meta["conjoint_role"] == "attribute"].copy()


def _resolve_question_type(section: str, question_type: str) -> str:
    """Human-facing question-type label, preferring the section identity."""
    if section in SECTION_QUESTION_TYPE:
        return SECTION_QUESTION_TYPE[section]
    return QUESTION_TYPE_LABEL.get(question_type, question_type or "rating")


def _build_prompt(feature_name: str, status: str) -> str:
    """Default question prompt (attribute_schema.md §7 worded example)."""
    if status == STATUS_ACTIVE:
        return f"How desirable is each level of '{feature_name}'?"
    return f"'{feature_name}' (auxiliary question — not modelled in the MVP)."


def _build_question(row: pd.Series) -> AttributeQuestion:
    """Turn one canonicalised attribute row into an :class:`AttributeQuestion`."""
    feature_name = str(row["feature_name"]).strip()
    section = str(row["conjoint_section"]).strip()
    question_type = str(row["conjoint_question_type"]).strip()

    labels = pp.split_semicolon(row["conjoint_levels"])
    codes = pp.derive_level_codes(labels, pp.split_semicolon(row["conjoint_level_codes"]))
    levels = tuple(Level(code=code, label=label) for code, label in zip(codes, labels))

    status = STATUS_ACTIVE if section == ACTIVE_SECTION else STATUS_OPTIONAL
    scale = Scale(RATING_SCALE_MIN, RATING_SCALE_MAX) if status == STATUS_ACTIVE else None

    return AttributeQuestion(
        feature_name=feature_name,
        description=str(row["description"]).strip(),
        section=section,
        question_type=_resolve_question_type(section, question_type),
        prompt=_build_prompt(feature_name, status),
        levels=levels,
        status=status,
        scale=scale,
    )


def build_questionnaire(meta_or_workbook: PathLike | pd.DataFrame) -> QuestionnaireSpec:
    """Build a :class:`QuestionnaireSpec` from a workbook path or metadata frame.

    ``meta_or_workbook`` may be either a path to an ``*.xlsx`` workbook (its
    ``Feature_data`` sheet is read and canonicalised) or an already-canonicalised
    ``Feature_data`` ``DataFrame`` (the output of
    :func:`preprocessing.normalize_metadata`). Returns a new spec; the input is
    never mutated.
    """
    meta = _load_metadata(meta_or_workbook)
    attribute_rows = _attribute_rows(meta)
    questions = tuple(_build_question(row) for _, row in attribute_rows.iterrows())
    return QuestionnaireSpec(attributes=questions)


def _load_metadata(meta_or_workbook: PathLike | pd.DataFrame) -> pd.DataFrame:
    """Read + canonicalise ``Feature_data`` (reusing :mod:`preprocessing`)."""
    if isinstance(meta_or_workbook, pd.DataFrame):
        return meta_or_workbook
    excel_path = Path(meta_or_workbook)
    pp.require_sheets(excel_path, pp.DATA_SHEET, pp.META_SHEET)
    meta_raw = pd.read_excel(excel_path, sheet_name=pp.META_SHEET)
    warnings: list[str] = []
    meta = pp.normalize_metadata(meta_raw, warnings)
    return pp.enforce_identifier_rules(meta, warnings)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def spec_to_dict(spec: QuestionnaireSpec) -> dict[str, object]:
    """Convert a :class:`QuestionnaireSpec` to a JSON-serialisable dict."""
    return {
        "version": spec.version,
        "scale": asdict(spec.scale),
        "attributes": [_question_to_dict(attr) for attr in spec.attributes],
    }


def _question_to_dict(attr: AttributeQuestion) -> dict[str, object]:
    payload: dict[str, object] = {
        "feature_name": attr.feature_name,
        "description": attr.description,
        "section": attr.section,
        "question_type": attr.question_type,
        "prompt": attr.prompt,
        "levels": [asdict(level) for level in attr.levels],
        "status": attr.status,
    }
    if attr.scale is not None:
        payload["scale"] = asdict(attr.scale)
    return payload


def spec_from_dict(payload: dict[str, object]) -> QuestionnaireSpec:
    """Inverse of :func:`spec_to_dict`; rebuild a spec from parsed JSON."""
    if not isinstance(payload, dict):
        raise ValueError("questionnaire spec must be a JSON object")
    raw_attributes = payload.get("attributes", [])
    if not isinstance(raw_attributes, list):
        raise ValueError("'attributes' must be a list")
    attributes = tuple(_question_from_dict(item) for item in raw_attributes)
    scale = _scale_from_dict(payload.get("scale"))
    version = str(payload.get("version", SPEC_VERSION))
    return QuestionnaireSpec(attributes=attributes, scale=scale, version=version)


def _scale_from_dict(raw: object) -> Scale:
    if isinstance(raw, dict) and "min" in raw and "max" in raw:
        return Scale(min=int(raw["min"]), max=int(raw["max"]))
    return Scale(RATING_SCALE_MIN, RATING_SCALE_MAX)


def _question_from_dict(item: object) -> AttributeQuestion:
    if not isinstance(item, dict):
        raise ValueError("each attribute entry must be a JSON object")
    levels = tuple(
        Level(code=str(lv["code"]), label=str(lv["label"]))
        for lv in item.get("levels", [])
    )
    raw_scale = item.get("scale")
    scale = _scale_from_dict(raw_scale) if isinstance(raw_scale, dict) else None
    return AttributeQuestion(
        feature_name=str(item["feature_name"]),
        description=str(item.get("description", "")),
        section=str(item.get("section", "")),
        question_type=str(item.get("question_type", "")),
        prompt=str(item.get("prompt", "")),
        levels=levels,
        status=str(item.get("status", STATUS_OPTIONAL)),
        scale=scale,
    )


def write_spec(spec: QuestionnaireSpec, path: PathLike) -> Path:
    """Write ``questionnaire_spec.json`` (pretty-printed, UTF-8). Returns path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(spec_to_dict(spec), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def read_spec(path: PathLike) -> QuestionnaireSpec:
    """Read a ``questionnaire_spec.json`` written by :func:`write_spec`."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return spec_from_dict(payload)


# ---------------------------------------------------------------------------
# responses.csv template + validation (shared contract with Module 3)
# ---------------------------------------------------------------------------
def response_columns(spec: QuestionnaireSpec) -> list[str]:
    """Ordered B-1 rating columns built via :func:`conjoint.io.response_column`.

    One column per (active attribute, level) in workbook order, so the resulting
    list is exactly what Module 3's design matrix expects.
    """
    columns: list[str] = []
    for attr in spec.active_attributes:
        for level in attr.levels:
            columns.append(response_column(attr.feature_name, level.code))
    return columns


def responses_template(spec: QuestionnaireSpec) -> pd.DataFrame:
    """Return an empty ``responses.csv`` frame (``respondent`` + B-1 columns)."""
    columns = [RESPONDENT_COL, *response_columns(spec)]
    return pd.DataFrame(columns=columns)


def write_responses_template(spec: QuestionnaireSpec, path: PathLike) -> Path:
    """Write the empty responses template CSV. Returns the written path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    responses_template(spec).to_csv(target, index=False)
    return target


def validate_responses(df: pd.DataFrame, spec: QuestionnaireSpec) -> list[str]:
    """Validate a responses frame against ``spec``; return a list of problems.

    An empty list means the frame is valid. Checks (in order):

    1. The ``respondent`` column is present.
    2. Every expected B-1 rating column is present; no unexpected extra columns.
    3. Every rating is an integer within the active scale ``[min, max]`` (blank
       cells are allowed — a partially-completed survey is not an error here).
    """
    problems: list[str] = []
    if RESPONDENT_COL not in df.columns:
        problems.append(f"missing required column '{RESPONDENT_COL}'")

    expected = response_columns(spec)
    actual = [col for col in df.columns if col != RESPONDENT_COL]
    problems.extend(_column_problems(expected, actual))
    problems.extend(_rating_problems(df, expected, spec.scale))
    return problems


def _column_problems(expected: list[str], actual: list[str]) -> list[str]:
    expected_set, actual_set = set(expected), set(actual)
    problems: list[str] = []
    for column in expected:
        if column not in actual_set:
            problems.append(f"missing rating column '{column}'")
    for column in actual:
        if column not in expected_set:
            problems.append(f"unexpected column '{column}'")
    return problems


def _rating_problems(df: pd.DataFrame, expected: list[str], scale: Scale) -> list[str]:
    problems: list[str] = []
    for column in expected:
        if column not in df.columns:
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        for idx, raw in df[column].items():
            if pd.isna(raw) or (isinstance(raw, str) and not raw.strip()):
                continue
            number = values.loc[idx]
            if pd.isna(number) or number != int(number):
                problems.append(f"row {idx}, column '{column}': non-integer rating {raw!r}")
            elif not scale.min <= int(number) <= scale.max:
                problems.append(
                    f"row {idx}, column '{column}': rating {raw!r} outside "
                    f"[{scale.min}, {scale.max}]"
                )
    return problems
