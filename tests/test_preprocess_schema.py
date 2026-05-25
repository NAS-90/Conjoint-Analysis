"""Schema validation + attribute_column_map tests for Module 1.

These exercise the conjoint metadata enforcement (attribute_schema.md §4) and
the attribute_column_map artifact against the ``sample_workbook`` fixture in
``conftest.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import preprocessing as pp
from conjoint import io


# ---------------------------------------------------------------------------
# Helpers for building mutated workbooks from the fixture
# ---------------------------------------------------------------------------
def _read_sheets(path: Path) -> dict[str, pd.DataFrame]:
    xl = pd.ExcelFile(path)
    return {name: pd.read_excel(path, sheet_name=name) for name in xl.sheet_names}


def _write_sheets(sheets: dict[str, pd.DataFrame], path: Path) -> Path:
    with pd.ExcelWriter(path) as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


def _run(path: Path, tmp_path: Path) -> pp.PreprocessResult:
    return pp.preprocess_workbook(
        excel_path=path,
        output_path=tmp_path / "out.csv",
        attribute_map=tmp_path / "attribute_column_map.json",
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_sample_workbook_preprocesses(sample_workbook: Path, tmp_path: Path) -> None:
    result = _run(sample_workbook, tmp_path)
    assert result.data_rows == 3
    assert (tmp_path / "out.csv").exists()
    assert result.attribute_map_path == tmp_path / "attribute_column_map.json"


# ---------------------------------------------------------------------------
# Rule 1 — required sheets
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_missing_required_sheet_raises(sample_workbook: Path, tmp_path: Path) -> None:
    sheets = _read_sheets(sample_workbook)
    del sheets["Feature_data"]
    broken = _write_sheets(sheets, tmp_path / "broken.xlsx")
    with pytest.raises(pp.PreprocessError, match="Feature_data"):
        _run(broken, tmp_path)


# ---------------------------------------------------------------------------
# Rule 3 / required columns — missing required metadata column
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_missing_required_column_raises(sample_workbook: Path, tmp_path: Path) -> None:
    sheets = _read_sheets(sample_workbook)
    sheets["Feature_data"] = sheets["Feature_data"].drop(columns=["data_types"])
    broken = _write_sheets(sheets, tmp_path / "broken.xlsx")
    with pytest.raises(pp.PreprocessError, match="data_types"):
        _run(broken, tmp_path)


# ---------------------------------------------------------------------------
# Rule 4 — illegal enum value
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_illegal_conjoint_role_raises(sample_workbook: Path, tmp_path: Path) -> None:
    sheets = _read_sheets(sample_workbook)
    meta = sheets["Feature_data"]
    meta.loc[meta["feature_name"] == "engine", "conjoint_role"] = "bogus_role"
    broken = _write_sheets(sheets, tmp_path / "broken.xlsx")
    with pytest.raises(pp.PreprocessError, match="conjoint_role"):
        _run(broken, tmp_path)


@pytest.mark.unit
def test_illegal_data_type_is_warning_and_skips(
    sample_workbook: Path, tmp_path: Path
) -> None:
    """Unsupported data_types is documented as a warning + skip, not a hard fail."""
    sheets = _read_sheets(sample_workbook)
    meta = sheets["Feature_data"]
    meta.loc[meta["feature_name"] == "has_cabin", "data_types"] = "weird"
    workbook = _write_sheets(sheets, tmp_path / "wb.xlsx")
    result = _run(workbook, tmp_path)
    assert any("has_cabin" in w and "weird" in w for w in result.warnings)
    assert all(fr.feature_name != "has_cabin" for fr in result.feature_results)


# ---------------------------------------------------------------------------
# Rule 8 — attribute needs >=2 levels + valid question type
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_attribute_with_one_level_raises(sample_workbook: Path, tmp_path: Path) -> None:
    sheets = _read_sheets(sample_workbook)
    meta = sheets["Feature_data"]
    meta.loc[meta["feature_name"] == "engine", "conjoint_levels"] = "basic"
    broken = _write_sheets(sheets, tmp_path / "broken.xlsx")
    with pytest.raises(pp.PreprocessError, match="(?i)rule 8|>=2"):
        _run(broken, tmp_path)


@pytest.mark.unit
def test_attribute_with_empty_levels_raises(sample_workbook: Path, tmp_path: Path) -> None:
    sheets = _read_sheets(sample_workbook)
    meta = sheets["Feature_data"]
    meta.loc[meta["feature_name"] == "engine", "conjoint_levels"] = ""
    broken = _write_sheets(sheets, tmp_path / "broken.xlsx")
    with pytest.raises(pp.PreprocessError, match="(?i)rule 8|>=2"):
        _run(broken, tmp_path)


@pytest.mark.unit
def test_attribute_with_invalid_question_type_raises(
    sample_workbook: Path, tmp_path: Path
) -> None:
    sheets = _read_sheets(sample_workbook)
    meta = sheets["Feature_data"]
    meta.loc[meta["feature_name"] == "engine", "conjoint_question_type"] = "guess"
    broken = _write_sheets(sheets, tmp_path / "broken.xlsx")
    with pytest.raises(pp.PreprocessError, match="conjoint_question_type"):
        _run(broken, tmp_path)


# ---------------------------------------------------------------------------
# Rule 10 — identifier auto-correction (warn, do not hard-fail)
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_identifier_row_auto_corrected(sample_workbook: Path, tmp_path: Path) -> None:
    sheets = _read_sheets(sample_workbook)
    meta = sheets["Feature_data"]
    # Misconfigure the product_id identifier: include it + wrong role.
    meta.loc[meta["feature_name"] == "product_id", "included_in_analysis"] = "yes"
    meta.loc[meta["feature_name"] == "product_id", "conjoint_role"] = "attribute"
    workbook = _write_sheets(sheets, tmp_path / "wb.xlsx")
    result = _run(workbook, tmp_path)
    assert any("product_id" in w and "rule 10" in w for w in result.warnings)
    # product_id must not appear as a produced feature (forced to included=no).
    assert all(fr.feature_name != "product_id" for fr in result.feature_results)


# ---------------------------------------------------------------------------
# Backward compatibility — workbook without any conjoint columns
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_legacy_workbook_without_conjoint_columns(tmp_path: Path) -> None:
    edited = pd.DataFrame(
        {"product": ["A", "B"], "price": [100.0, 200.0], "rating": [3.0, 4.5]}
    )
    feature_data = pd.DataFrame(
        [
            {
                "feature_name": "price",
                "data_types": "metric",
                "included_in_analysis": "yes",
                "normalization_method": "z-score",
                "ideal_direction": "lower",
            },
            {
                "feature_name": "rating",
                "data_types": "metric",
                "included_in_analysis": "yes",
                "normalization_method": "min-max",
                "ideal_direction": "higher",
            },
        ]
    )
    path = _write_sheets({"Edited": edited, "Feature_data": feature_data}, tmp_path / "legacy.xlsx")
    result = _run(path, tmp_path)
    assert result.output_feature_count == 2
    # No conjoint attributes -> empty attribute map.
    mapping = io.read_attribute_map(tmp_path / "attribute_column_map.json")
    assert mapping == {}


# ---------------------------------------------------------------------------
# attribute_column_map content
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_attribute_map_keys_and_counts(sample_workbook: Path, tmp_path: Path) -> None:
    result = _run(sample_workbook, tmp_path)
    mapping = io.read_attribute_map(tmp_path / "attribute_column_map.json")

    # Keys = the attribute features (engine, transmission_type, has_cabin).
    assert set(mapping) == {"engine", "transmission_type", "has_cabin"}
    # price is conjoint_role=skip; product_id is identifier -> excluded.
    assert "price" not in mapping
    assert "product_id" not in mapping

    # m_a equals the actual produced column count.
    for attr, entry in mapping.items():
        assert entry["m_a"] == len(entry["columns"])

    # transmission_type (3 nominal levels) expands to exactly 3 one-hot columns.
    assert mapping["transmission_type"]["m_a"] == 3
    # engine (2 nominal levels) -> 2 columns.
    assert mapping["engine"]["m_a"] == 2
    # has_cabin is a binary attribute -> single column (m_a == 1, not one-hot).
    assert mapping["has_cabin"]["m_a"] == 1


@pytest.mark.integration
def test_attribute_map_columns_match_output(sample_workbook: Path, tmp_path: Path) -> None:
    _run(sample_workbook, tmp_path)
    mapping = io.read_attribute_map(tmp_path / "attribute_column_map.json")
    output_columns = set(pd.read_csv(tmp_path / "out.csv").columns)
    for entry in mapping.values():
        assert set(entry["columns"]).issubset(output_columns)


@pytest.mark.integration
def test_attribute_map_written_by_conjoint_io(sample_workbook: Path, tmp_path: Path) -> None:
    """The map is valid JSON readable through the shared contract loader."""
    map_path = tmp_path / "attribute_column_map.json"
    _run(sample_workbook, tmp_path)
    raw = json.loads(map_path.read_text(encoding="utf-8"))
    assert raw == io.read_attribute_map(map_path)


# ---------------------------------------------------------------------------
# Level-code defaulting
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_level_codes_default_to_slug_when_omitted(
    sample_workbook: Path, tmp_path: Path
) -> None:
    sheets = _read_sheets(sample_workbook)
    meta = sheets["Feature_data"]
    meta.loc[meta["feature_name"] == "transmission_type", "conjoint_levels"] = (
        "Not Synchronized; Power Shift"
    )
    meta.loc[meta["feature_name"] == "transmission_type", "conjoint_level_codes"] = ""
    workbook = _write_sheets(sheets, tmp_path / "wb.xlsx")
    _run(workbook, tmp_path)
    mapping = io.read_attribute_map(tmp_path / "attribute_column_map.json")
    assert mapping["transmission_type"]["conjoint_level_codes"] == [
        "not_synchronized",
        "power_shift",
    ]


@pytest.mark.unit
def test_slugify_level() -> None:
    assert pp.slugify_level("CVT") == "cvt"
    assert pp.slugify_level("Not Synchronized") == "not_synchronized"
    assert pp.slugify_level("16-speed (full)") == "16_speed_full"
