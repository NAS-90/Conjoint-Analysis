"""Tests for the conjoint demo + integration helpers (Integration wave).

Covers:

* ``scripts.build_demo_importance`` — the N=381 reference → ``importance.csv``
  converter (and that it matches the published reference).
* ``scripts.build_demo_workbook`` — the demo workbook generator and that it
  preprocesses into the expected one-hot ``attribute_column_map.json``.
* ``conjoint.questionnaire.responses_from_answers`` — assembling a contract-
  compliant ``responses.csv`` frame from collected answers.
* ``validation.validate_conjoint`` — the report generator's importance-match and
  neighbour-difference logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import preprocessing as pp  # noqa: E402
from conjoint import io  # noqa: E402
from conjoint import questionnaire as q  # noqa: E402
from scripts import build_demo_importance as bdi  # noqa: E402
from scripts import build_demo_workbook as bdw  # noqa: E402


# ---------------------------------------------------------------------------
# build_demo_importance
# ---------------------------------------------------------------------------
@pytest.fixture
def n381_reference(n381_fixture_dir: Path) -> dict:
    return json.loads(
        (n381_fixture_dir / "importance_reference.json").read_text(encoding="utf-8")
    )


@pytest.mark.unit
def test_reference_to_importance_columns_and_order(n381_reference: dict) -> None:
    frame = bdi.reference_to_importance(n381_reference)
    assert list(frame.columns) == list(io.IMPORTANCE_COLUMNS)
    # Attribute order follows the JSON insertion order.
    assert list(frame[io.ATTRIBUTE_COL]) == list(n381_reference.keys())


@pytest.mark.unit
def test_reference_to_importance_matches_reference(n381_reference: dict) -> None:
    frame = bdi.reference_to_importance(n381_reference)
    for _, row in frame.iterrows():
        ref = n381_reference[row[io.ATTRIBUTE_COL]]
        assert row[io.RELATIVE_IMPORTANCE_COL] == pytest.approx(
            ref["relative_importance"]
        )
        assert row[io.ABSOLUTE_IMPORTANCE_COL] == pytest.approx(
            ref["absolute_importance"]
        )


@pytest.mark.unit
def test_reference_to_importance_rejects_empty() -> None:
    with pytest.raises(ValueError):
        bdi.reference_to_importance({})


@pytest.mark.integration
def test_build_importance_round_trips_via_io(tmp_path: Path) -> None:
    out = tmp_path / "importance.csv"
    bdi.build(bdi.DEFAULT_REFERENCE, out)
    # Must be readable through the shared contract with the canonical columns.
    frame = io.read_importance(out)
    assert set(frame[io.ATTRIBUTE_COL]) == set(bdw.ATTRIBUTES)
    assert frame[io.RELATIVE_IMPORTANCE_COL].sum() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# build_demo_workbook
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_every_level_is_covered_by_a_config() -> None:
    levels = bdw.load_levels(bdw.DEFAULT_LEVELS)
    # _validate_codes raises if any level is missing from the configs.
    bdw._validate_codes(levels)
    for attr in bdw.ATTRIBUTES:
        used = {config[attr] for config in bdw.CONFIGURATIONS}
        known = {lv["code"] for lv in levels[attr]}
        assert used == known


@pytest.mark.unit
def test_feature_data_marks_attributes_and_identifier() -> None:
    levels = bdw.load_levels(bdw.DEFAULT_LEVELS)
    meta = bdw.build_feature_data_sheet(levels)
    by_name = {row["feature_name"]: row for _, row in meta.iterrows()}

    assert by_name[bdw.IDENTIFIER]["conjoint_role"] == "identifier"
    assert by_name[bdw.IDENTIFIER]["included_in_analysis"] == "no"
    for attr in bdw.ATTRIBUTES:
        assert by_name[attr]["conjoint_role"] == "attribute"
        assert by_name[attr]["conjoint_question_type"] == "rating"
        assert by_name[attr]["conjoint_section"] == "B1_rating"


@pytest.mark.integration
def test_demo_workbook_preprocesses_with_expected_attribute_map(tmp_path: Path) -> None:
    workbook = tmp_path / "conjoint_demo.xlsx"
    bdw.build(bdw.DEFAULT_LEVELS, workbook)

    out_csv = tmp_path / "preprocessed_output.csv"
    map_path = tmp_path / "attribute_column_map.json"
    pp.preprocess_workbook(workbook, out_csv, attribute_map=map_path)

    mapping = io.read_attribute_map(map_path)
    # All 7 attributes present; identifier excluded.
    assert set(mapping) == set(bdw.ATTRIBUTES)
    assert bdw.IDENTIFIER not in mapping

    levels = bdw.load_levels(bdw.DEFAULT_LEVELS)
    df = pd.read_csv(out_csv)
    total_columns = 0
    for attr in bdw.ATTRIBUTES:
        m_a = mapping[attr]["m_a"]
        # m_a equals the published level count (every level appears in the data).
        assert m_a == len(levels[attr])
        assert len(mapping[attr]["columns"]) == m_a
        for col in mapping[attr]["columns"]:
            assert col in df.columns
        total_columns += m_a
    assert df.shape == (len(bdw.CONFIGURATIONS), total_columns)


# ---------------------------------------------------------------------------
# responses_from_answers
# ---------------------------------------------------------------------------
@pytest.fixture
def demo_spec(tmp_path: Path) -> q.QuestionnaireSpec:
    workbook = tmp_path / "conjoint_demo.xlsx"
    bdw.build(bdw.DEFAULT_LEVELS, workbook)
    return q.build_questionnaire(workbook)


@pytest.mark.unit
def test_responses_from_answers_column_order_matches_contract(
    demo_spec: q.QuestionnaireSpec,
) -> None:
    columns = q.response_columns(demo_spec)
    answer = {col: 3 for col in columns}
    frame = q.responses_from_answers([answer], demo_spec)

    assert list(frame.columns) == [io.RESPONDENT_COL, *columns]
    assert list(frame[io.RESPONDENT_COL]) == [1]
    # Valid against the spec (all in-scale, no missing/extra columns).
    assert q.validate_responses(frame, demo_spec) == []


@pytest.mark.unit
def test_responses_from_answers_respects_respondent_ids(
    demo_spec: q.QuestionnaireSpec,
) -> None:
    columns = q.response_columns(demo_spec)
    answers = [{c: 2 for c in columns}, {c: 4 for c in columns}]
    frame = q.responses_from_answers(answers, demo_spec, respondent_ids=["a", "b"])
    assert list(frame[io.RESPONDENT_COL]) == ["a", "b"]


@pytest.mark.unit
def test_responses_from_answers_mismatched_ids_raise(
    demo_spec: q.QuestionnaireSpec,
) -> None:
    columns = q.response_columns(demo_spec)
    with pytest.raises(ValueError):
        q.responses_from_answers(
            [{c: 3 for c in columns}], demo_spec, respondent_ids=["a", "b"]
        )


@pytest.mark.integration
def test_responses_from_answers_feed_estimate(demo_spec: q.QuestionnaireSpec) -> None:
    """A built responses frame must aggregate through Module 3 without error."""
    from conjoint.estimate import aggregate_importance, estimate_utilities

    columns = q.response_columns(demo_spec)
    # Two respondents with differing ratings so OLS has signal.
    answers = [
        {c: (i % 5) + 1 for i, c in enumerate(columns)},
        {c: ((i + 2) % 5) + 1 for i, c in enumerate(columns)},
    ]
    frame = q.responses_from_answers(answers, demo_spec)

    # Grouping is inferred from the ``{attribute}__{level}`` column names, exactly
    # as the CLI does when no --attribute-levels file is supplied.
    utilities = estimate_utilities(frame)
    importance = aggregate_importance(utilities)
    assert set(importance[io.ATTRIBUTE_COL]) == set(bdw.ATTRIBUTES)
    assert importance[io.RELATIVE_IMPORTANCE_COL].sum() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# validate_conjoint (report generator logic)
# ---------------------------------------------------------------------------
def _neighbors_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Build a normalised product/neighbor/distance frame for tests."""
    return pd.DataFrame(rows, columns=["product", "neighbor", "distance"])


@pytest.mark.unit
def test_validate_conjoint_all_match_detects_equality() -> None:
    from validation import validate_conjoint as vc

    importance = pd.DataFrame(
        {
            io.ATTRIBUTE_COL: ["engine", "tank"],
            io.ABSOLUTE_IMPORTANCE_COL: [1.0, 2.0],
            io.RELATIVE_IMPORTANCE_COL: [0.4, 0.6],
        }
    )
    assert vc.all_match(importance, {"engine": 0.4, "tank": 0.6}) is True
    assert vc.all_match(importance, {"engine": 0.4, "tank": 0.59}) is False
    assert vc.all_match(importance, {"engine": 0.4}) is False  # missing attr


@pytest.mark.unit
def test_validate_conjoint_counts_reordered_products() -> None:
    from validation import validate_conjoint as vc

    technical = _neighbors_frame(
        [("A", "B", 1.0), ("A", "C", 2.0), ("B", "A", 1.0), ("B", "C", 1.5)]
    )
    # For A the weighted view swaps the top-2 ordering; for B it is unchanged.
    weighted = _neighbors_frame(
        [("A", "C", 0.5), ("A", "B", 0.9), ("B", "A", 0.4), ("B", "C", 0.7)]
    )
    assert vc._neighbors_differ(technical, weighted, "A", k=2) is True
    assert vc._neighbors_differ(technical, weighted, "B", k=2) is False
    assert vc.count_differing(technical, weighted, ["A", "B"], k=2) == 1


@pytest.mark.unit
def test_validate_conjoint_sample_prefers_differing() -> None:
    from validation import validate_conjoint as vc

    technical = _neighbors_frame(
        [("A", "B", 1.0), ("A", "C", 2.0), ("B", "A", 1.0), ("B", "C", 1.5)]
    )
    weighted = _neighbors_frame(
        [("A", "C", 0.5), ("A", "B", 0.9), ("B", "A", 0.4), ("B", "C", 0.7)]
    )
    # Only one slot: the differing product (A) must be chosen over the matching one.
    assert vc._pick_sample(technical, weighted, ["A", "B"], 1, 2) == ["A"]


@pytest.mark.integration
def test_validate_conjoint_build_report_round_trip(tmp_path: Path) -> None:
    """Build the demo artifacts in a temp dir and render the report end to end."""
    from validation import validate_conjoint as vc

    # Demo importance + workbook + technical/weighted neighbours.
    bdi.build(bdi.DEFAULT_REFERENCE, tmp_path / "importance.csv")
    workbook = tmp_path / "conjoint_demo.xlsx"
    bdw.build(bdw.DEFAULT_LEVELS, workbook)
    pre = tmp_path / "preprocessed_output.csv"
    amap = tmp_path / "attribute_column_map.json"
    pp.preprocess_workbook(workbook, pre, attribute_map=amap)

    import compute_distance_matrix as cdm

    X_scaled, columns, _ = cdm._prepare_scaled_matrix(str(pre))
    names = pd.read_excel(workbook, sheet_name="Edited")["product_id"].tolist()

    tech_dm = pd.DataFrame(
        cdm.compute_euclidean_distance_matrix(X_scaled), index=names, columns=names
    )
    cdm.build_neighbors_table(tech_dm, 5).to_csv(
        tmp_path / "nearest_neighbors.csv", index=False
    )

    importance = io.read_importance(tmp_path / "importance.csv")
    weights = cdm.build_weight_vector(columns, importance, io.read_attribute_map(amap))
    wt_dm = pd.DataFrame(
        cdm.weighted_distance_matrix(X_scaled, weights), index=names, columns=names
    )
    cdm.build_neighbors_table(wt_dm, 5).to_csv(
        tmp_path / "nearest_neighbors_weighted.csv", index=False
    )

    report = vc.build_report(tmp_path, bdi.DEFAULT_REFERENCE)
    assert "matches the published reference" in report
    # The weighting must change at least one product's ordering.
    technical = vc.load_neighbors_table(tmp_path / "nearest_neighbors.csv")
    weighted = vc.load_neighbors_table(tmp_path / "nearest_neighbors_weighted.csv")
    products = sorted(technical["product"].unique())
    assert vc.count_differing(technical, weighted, products, vc.NEIGHBOR_K) > 0
