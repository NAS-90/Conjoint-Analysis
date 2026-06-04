"""Cleaned-workbook assembly tests (TDD).

``clean_workbook`` must emit a 2-sheet workbook (``Edited`` + ``Feature_data``)
that the universal preprocessor can consume directly, replacing the noisy raw
workbook in the pipeline.
"""

from __future__ import annotations

import pandas as pd
import pytest

from smartphone_cleaning import clean, extract
from preprocessing import (
    ALLOWED_IDEALS,
    ALLOWED_NORMS,
    ALLOWED_TYPES,
    preprocess_workbook,
)

THIN = " "

RAW_ROWS = [
    {
        "model": "Galaxy Test Pro",
        "price": "₹54,999.00",
        "rating": "89.0",
        "sim": "Dual Sim, 5G",
        "processor": f"Snapdragon 8 Gen2, Octa Core, 3.2{THIN}GHz Processor",
        "ram": f"12{THIN}GB RAM, 256{THIN}GB inbuilt",
        "battery": f"5000{THIN}mAh Battery with 100W Fast Charging",
        "display": f"6.7 inches, 1440 x 3216 px, 120 Hz Display with Punch Hole",
        "camera": f"50{THIN}MP + 8{THIN}MP + 2{THIN}MP Triple Rear & 16{THIN}MP Front Camera",
        "card": "Memory Card Not Supported",
        "os": "Android v13",
    },
    {
        "model": "Nokia 2660 Flip",
        "price": "₹4,649.00",
        "rating": float("nan"),
        "sim": "Dual Sim, 3G, 4G",
        "processor": "No Wifi",
        "ram": "Unisoc T107",
        "battery": f"48{THIN}MB RAM, 128{THIN}MB inbuilt",
        "display": f"1450{THIN}mAh Battery",
        "camera": "2.8 inches, 240 x 320 px Display",
        "card": "Dual Display",
        "os": "0.3 MP Rear Camera",
    },
]


def _write_raw(path):
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(RAW_ROWS).to_excel(writer, sheet_name="Edited", index=False)


def test_feature_data_is_valid_for_every_clean_column():
    fd = clean.build_feature_data()
    # one metadata row per analysed clean column (model is the identifier, excluded)
    feature_names = set(fd["feature_name"])
    expected = set(extract.CLEAN_COLUMNS) - {"model"}
    assert feature_names == expected
    assert set(fd["data_types"]) <= ALLOWED_TYPES
    assert set(fd["normalization_method"]) <= ALLOWED_NORMS
    assert set(fd["ideal_direction"]) <= ALLOWED_IDEALS
    assert (fd["included_in_analysis"] == "yes").all()


def test_clean_workbook_roundtrip(tmp_path):
    src = tmp_path / "raw.xlsx"
    dst = tmp_path / "cleaned.xlsx"
    _write_raw(src)

    report = clean.clean_workbook(src, dst)
    assert report.n_rows == 2
    assert dst.exists()

    sheets = pd.ExcelFile(dst).sheet_names
    assert sheets == ["Edited", "Feature_data"]

    edited = pd.read_excel(dst, sheet_name="Edited")
    assert list(edited.columns) == extract.CLEAN_COLUMNS
    assert edited.loc[1, "battery_mah"] == pytest.approx(1450.0)  # shifted row recovered


def test_cleaned_workbook_feeds_universal_preprocessor(tmp_path):
    """End-to-end: cleaned workbook must preprocess without the 296-column blow-up."""
    src = tmp_path / "raw.xlsx"
    dst = tmp_path / "cleaned.xlsx"
    out = tmp_path / "preprocessed.csv"
    _write_raw(src)
    clean.clean_workbook(src, dst)

    result = preprocess_workbook(dst, out)
    # 13 numeric + chip_brand(2) + os_family(2) one-hots on this 2-row sample:
    # the point is it is a couple of dozen columns, not hundreds.
    assert result.output_feature_count < 30
    assert out.exists()
