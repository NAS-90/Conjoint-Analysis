"""Tests for Module 2 — questionnaire generator (core).

Exercises :mod:`conjoint.questionnaire` against the ``sample_workbook`` fixture
in ``conftest.py`` (engine[basic, premium], transmission_type[manual,
powershift, cvt], has_cabin[no, yes] as B-1 rating attributes; price skipped;
product_id identifier). The response-template columns are asserted to be built
via :func:`conjoint.io.response_column` so they match Module 3's expected input.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from conjoint import io
from conjoint import questionnaire as q


# Attributes, in workbook order, with their ordered level codes.
EXPECTED_ATTRIBUTES = [
    ("engine", ["basic", "premium"]),
    ("transmission_type", ["manual", "powershift", "cvt"]),
    ("has_cabin", ["no", "yes"]),
]


def _expected_response_columns() -> list[str]:
    """Build the expected responses columns straight from the shared contract."""
    columns = [io.RESPONDENT_COL]
    for feature, codes in EXPECTED_ATTRIBUTES:
        columns.extend(io.response_column(feature, code) for code in codes)
    return columns


# ---------------------------------------------------------------------------
# Spec content
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_spec_contains_exactly_rating_attributes(sample_workbook: Path) -> None:
    spec = q.build_questionnaire(sample_workbook)

    names = [attr.feature_name for attr in spec.attributes]
    assert names == ["engine", "transmission_type", "has_cabin"]
    # price (skip) and product_id (identifier) must not appear.
    assert "price" not in names
    assert "product_id" not in names


@pytest.mark.unit
def test_spec_level_counts_and_order(sample_workbook: Path) -> None:
    spec = q.build_questionnaire(sample_workbook)
    by_name = {attr.feature_name: attr for attr in spec.attributes}

    for feature, codes in EXPECTED_ATTRIBUTES:
        attr = by_name[feature]
        assert [level.code for level in attr.levels] == codes
        assert len(attr.levels) == len(codes)


@pytest.mark.unit
def test_b1_attributes_are_active_with_scale(sample_workbook: Path) -> None:
    spec = q.build_questionnaire(sample_workbook)
    for attr in spec.attributes:
        assert attr.section == "B1_rating"
        assert attr.status == "active"
        assert attr.question_type == "rating"
        assert attr.scale == q.Scale(1, 5)
    assert len(spec.active_attributes) == 3


@pytest.mark.unit
def test_non_b1_section_flagged_optional() -> None:
    """A B2_importance attribute still emits an entry but is flagged optional."""
    meta = pd.DataFrame(
        [
            {
                "feature_name": "engine",
                "description": "Engine package",
                "conjoint_role": "attribute",
                "conjoint_levels": "basic; premium",
                "conjoint_level_codes": "basic; premium",
                "conjoint_question_type": "pairwise",
                "conjoint_section": "B2_importance",
            }
        ]
    )
    spec = q.build_questionnaire(meta)
    assert len(spec.attributes) == 1
    attr = spec.attributes[0]
    assert attr.status == "optional"
    assert attr.section == "B2_importance"
    assert attr.question_type == "importance"
    assert attr.scale is None
    # Optional (non-B1) attributes contribute no rating columns.
    assert spec.active_attributes == ()
    assert q.response_columns(spec) == []


# ---------------------------------------------------------------------------
# responses_template — must match Module 3's expected input exactly
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_responses_template_columns(sample_workbook: Path) -> None:
    spec = q.build_questionnaire(sample_workbook)
    template = q.responses_template(spec)

    assert list(template.columns) == _expected_response_columns()
    # Empty frame: header only, no rows.
    assert len(template) == 0


@pytest.mark.unit
def test_responses_template_columns_built_via_io_response_column(
    sample_workbook: Path,
) -> None:
    """Every non-respondent column round-trips through conjoint.io helpers."""
    spec = q.build_questionnaire(sample_workbook)
    columns = list(q.responses_template(spec).columns)

    assert columns[0] == io.RESPONDENT_COL
    rebuilt = [
        io.response_column(*io.split_response_column(col)) for col in columns[1:]
    ]
    assert rebuilt == columns[1:]
    # Concretely the engine/transmission/has_cabin columns.
    assert columns[1] == io.response_column("engine", "basic")
    assert columns[2] == io.response_column("engine", "premium")
    assert columns[-1] == io.response_column("has_cabin", "yes")


# ---------------------------------------------------------------------------
# validate_responses
# ---------------------------------------------------------------------------
def _valid_responses(spec: q.QuestionnaireSpec) -> pd.DataFrame:
    frame = q.responses_template(spec)
    rating_cols = q.response_columns(spec)
    row = {io.RESPONDENT_COL: "r1"}
    row.update({col: 3 for col in rating_cols})
    return pd.concat([frame, pd.DataFrame([row])], ignore_index=True)


@pytest.mark.unit
def test_validate_responses_accepts_valid_frame(sample_workbook: Path) -> None:
    spec = q.build_questionnaire(sample_workbook)
    assert q.validate_responses(_valid_responses(spec), spec) == []


@pytest.mark.unit
def test_validate_responses_flags_missing_column(sample_workbook: Path) -> None:
    spec = q.build_questionnaire(sample_workbook)
    frame = _valid_responses(spec)
    dropped = io.response_column("engine", "basic")
    frame = frame.drop(columns=[dropped])

    problems = q.validate_responses(frame, spec)
    assert any(dropped in problem and "missing" in problem for problem in problems)


@pytest.mark.unit
def test_validate_responses_flags_out_of_range_rating(sample_workbook: Path) -> None:
    spec = q.build_questionnaire(sample_workbook)
    frame = _valid_responses(spec)
    target = io.response_column("transmission_type", "manual")
    frame.loc[0, target] = 9  # scale is 1..5

    problems = q.validate_responses(frame, spec)
    assert any(target in problem and "outside" in problem for problem in problems)


@pytest.mark.unit
def test_validate_responses_flags_missing_respondent_column(
    sample_workbook: Path,
) -> None:
    spec = q.build_questionnaire(sample_workbook)
    frame = _valid_responses(spec).drop(columns=[io.RESPONDENT_COL])
    problems = q.validate_responses(frame, spec)
    assert any(io.RESPONDENT_COL in problem for problem in problems)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_spec_round_trip_preserves_structure(
    sample_workbook: Path, tmp_path: Path
) -> None:
    spec = q.build_questionnaire(sample_workbook)
    path = tmp_path / "questionnaire_spec.json"
    q.write_spec(spec, path)

    restored = q.read_spec(path)
    assert restored == spec
    # The serialised form is also valid, readable JSON.
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [a["feature_name"] for a in payload["attributes"]] == [
        "engine",
        "transmission_type",
        "has_cabin",
    ]


@pytest.mark.integration
def test_write_responses_template_file_roundtrips(
    sample_workbook: Path, tmp_path: Path
) -> None:
    spec = q.build_questionnaire(sample_workbook)
    path = tmp_path / "responses_template.csv"
    q.write_responses_template(spec, path)

    # Read back through the shared contract loader (validates respondent col).
    frame = io.read_responses(path)
    assert list(frame.columns) == _expected_response_columns()
    assert len(frame) == 0
