"""Tests for the shared conjoint I/O contract (conjoint.io)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from conjoint import io


# ---------------------------------------------------------------------------
# Column naming helpers
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.parametrize(
    ("attribute", "level_code"),
    [
        ("transmission_type", "cvt"),
        ("engine", "basic"),
        ("number_of_gears", "16_speed"),  # level code with single underscores
    ],
)
def test_response_column_round_trip(attribute: str, level_code: str) -> None:
    column = io.response_column(attribute, level_code)
    assert column == f"{attribute}{io.LEVEL_SEP}{level_code}"
    assert io.split_response_column(column) == (attribute, level_code)


@pytest.mark.unit
def test_response_column_rejects_empty_parts() -> None:
    with pytest.raises(ValueError):
        io.response_column("", "cvt")
    with pytest.raises(ValueError):
        io.response_column("engine", "")


@pytest.mark.unit
def test_response_column_rejects_embedded_separator() -> None:
    with pytest.raises(ValueError):
        io.response_column("engine__x", "basic")
    with pytest.raises(ValueError):
        io.response_column("engine", "ba__sic")


@pytest.mark.unit
def test_split_response_column_requires_separator() -> None:
    with pytest.raises(ValueError):
        io.split_response_column("engine_basic")


@pytest.mark.unit
def test_split_response_column_splits_on_first_separator() -> None:
    # Attribute stays intact even if the level code embeds a single underscore.
    assert io.split_response_column("number_of_gears__16_speed") == (
        "number_of_gears",
        "16_speed",
    )


@pytest.mark.unit
@pytest.mark.parametrize("column", ["__basic", "engine__", "__"])
def test_split_response_column_rejects_empty_part(column: str) -> None:
    with pytest.raises(ValueError):
        io.split_response_column(column)


# ---------------------------------------------------------------------------
# responses.csv
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_responses_round_trip(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            io.RESPONDENT_COL: [1, 2, 3],
            io.response_column("engine", "basic"): [1, 4, 5],
            io.response_column("engine", "premium"): [5, 2, 3],
        }
    )
    path = tmp_path / "responses.csv"
    io.write_responses(df, path)
    loaded = io.read_responses(path)
    pd.testing.assert_frame_equal(loaded, df)


@pytest.mark.unit
def test_write_responses_requires_respondent(tmp_path: Path) -> None:
    df = pd.DataFrame({io.response_column("engine", "basic"): [1, 2]})
    with pytest.raises(ValueError, match="respondent"):
        io.write_responses(df, tmp_path / "responses.csv")


@pytest.mark.unit
def test_read_responses_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        io.read_responses(tmp_path / "nope.csv")


# ---------------------------------------------------------------------------
# utilities.csv
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_utilities_round_trip(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            io.RESPONDENT_COL: [1, 2],
            io.response_column("engine", "basic"): [-30.41, -28.0],
            io.response_column("engine", "premium"): [30.41, 28.0],
        }
    )
    path = tmp_path / "utilities.csv"
    io.write_utilities(df, path)
    loaded = io.read_utilities(path)
    pd.testing.assert_frame_equal(loaded, df)


# ---------------------------------------------------------------------------
# importance.csv
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_importance_round_trip(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            io.ATTRIBUTE_COL: ["engine", "transmission_type"],
            io.ABSOLUTE_IMPORTANCE_COL: [60.82, 96.54],
            io.RELATIVE_IMPORTANCE_COL: [0.3865, 0.6135],
        }
    )
    path = tmp_path / "importance.csv"
    io.write_importance(df, path)
    loaded = io.read_importance(path)
    assert list(loaded.columns) == list(io.IMPORTANCE_COLUMNS)
    pd.testing.assert_frame_equal(loaded, df)


@pytest.mark.unit
def test_write_importance_reorders_and_drops_extra_columns(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "extra": ["x", "y"],
            io.RELATIVE_IMPORTANCE_COL: [0.4, 0.6],
            io.ABSOLUTE_IMPORTANCE_COL: [4.0, 6.0],
            io.ATTRIBUTE_COL: ["a", "b"],
        }
    )
    path = tmp_path / "importance.csv"
    io.write_importance(df, path)
    loaded = io.read_importance(path)
    assert list(loaded.columns) == list(io.IMPORTANCE_COLUMNS)


@pytest.mark.unit
def test_read_importance_missing_column(tmp_path: Path) -> None:
    bad = pd.DataFrame({io.ATTRIBUTE_COL: ["a"], io.ABSOLUTE_IMPORTANCE_COL: [1.0]})
    path = tmp_path / "importance.csv"
    bad.to_csv(path, index=False)
    with pytest.raises(ValueError, match="relative_importance"):
        io.read_importance(path)


# ---------------------------------------------------------------------------
# attribute_column_map.json
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_attribute_map_round_trip(tmp_path: Path) -> None:
    mapping = {
        "transmission_type": {
            "columns": ["transmission_type_cvt", "transmission_type_powershift"],
            "m_a": 2,
            "conjoint_levels": ["powershift", "CVT"],
            "conjoint_level_codes": ["powershift", "cvt"],
        }
    }
    path = tmp_path / "attribute_column_map.json"
    io.write_attribute_map(mapping, path)
    assert io.read_attribute_map(path) == mapping


@pytest.mark.unit
def test_write_attribute_map_rejects_non_dict(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        io.write_attribute_map(["not", "a", "dict"], tmp_path / "m.json")  # type: ignore[arg-type]


@pytest.mark.unit
def test_attribute_map_preserves_unicode(tmp_path: Path) -> None:
    mapping = {"price": {"columns": ["price"], "m_a": 1, "unit": "R$ €"}}
    path = tmp_path / "m.json"
    io.write_attribute_map(mapping, path)
    assert io.read_attribute_map(path)["price"]["unit"] == "R$ €"


@pytest.mark.unit
def test_read_attribute_map_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        io.read_attribute_map(path)
