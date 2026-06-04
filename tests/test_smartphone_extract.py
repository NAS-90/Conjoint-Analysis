"""Content-based, shift-robust row extraction tests (TDD).

The raw workbook has ~13 feature-phone rows where a spurious connectivity token
(``"No Wifi"`` / ``"No 3G"``) is inserted at the ``processor`` column, shifting
every later attribute one cell to the right. Locating attributes by *content*
(not column position) must recover the true values for those rows while leaving
well-formed rows untouched.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from smartphone_cleaning import extract

THIN = " "  # U+2009


def is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)


NORMAL_ROW = {
    "model": "Galaxy Test Pro",
    "price": "₹54,999.00",
    "rating": "89.0",
    "sim": "Dual Sim, 3G, 4G, 5G, VoLTE, Wi-Fi, NFC",
    "processor": f"Snapdragon 8 Gen2, Octa Core, 3.2{THIN}GHz Processor",
    "ram": f"12{THIN}GB RAM, 256{THIN}GB inbuilt",
    "battery": f"5000{THIN}mAh Battery with 100W Fast Charging",
    "display": f"6.7 inches, 1440{THIN}x{THIN}3216{THIN}px, 120 Hz Display with Punch Hole",
    "camera": f"50{THIN}MP + 48{THIN}MP + 32{THIN}MP Triple Rear & 16{THIN}MP Front Camera",
    "card": "Memory Card Not Supported",
    "os": "Android v13",
}

# Nokia 2660 Flip — real shifted row: "No Wifi" pushed everything right by one.
SHIFTED_ROW = {
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
}


def test_normal_row_extracts_every_attribute():
    out = extract.clean_row(NORMAL_ROW)
    assert out["price"] == pytest.approx(54999.0)
    assert out["rating"] == pytest.approx(89.0)
    assert out["processor_ghz"] == pytest.approx(3.2)
    assert out["processor_cores"] == 8
    assert out["chip_brand"] == "Snapdragon"
    assert out["ram_gb"] == pytest.approx(12.0)
    assert out["storage_gb"] == pytest.approx(256.0)
    assert out["battery_mah"] == pytest.approx(5000.0)
    assert out["display_size_in"] == pytest.approx(6.7)
    assert out["display_refresh_hz"] == pytest.approx(120.0)
    assert out["camera_main_mp"] == pytest.approx(50.0)
    assert out["camera_front_mp"] == pytest.approx(16.0)
    assert out["camera_rear_count"] == 3
    assert out["card_supported"] == "No"
    assert out["os_family"] == "Android"


def test_shifted_row_is_realigned_by_content():
    out = extract.clean_row(SHIFTED_ROW)
    # battery value lives in the 'display' column, display in 'camera', etc.
    assert out["battery_mah"] == pytest.approx(1450.0)
    assert out["display_size_in"] == pytest.approx(2.8)
    assert out["camera_main_mp"] == pytest.approx(0.3)
    assert out["ram_gb"] == pytest.approx(48 / 1024)
    assert out["storage_gb"] == pytest.approx(128 / 1024)
    assert out["chip_brand"] == "Unisoc"  # 'Unisoc T107' sat in the 'ram' column
    assert is_nan(out["processor_ghz"])  # feature phone: no clock stated
    assert out["price"] == pytest.approx(4649.0)


def test_refresh_defaults_to_60_when_absent_but_display_present():
    row = dict(NORMAL_ROW, display="6.1 inches, 1170 x 2532 px Display with Small Notch")
    out = extract.clean_row(row)
    assert out["display_size_in"] == pytest.approx(6.1)
    assert out["display_refresh_hz"] == pytest.approx(60.0)


def test_no_rear_camera_is_zero_not_missing():
    row = dict(NORMAL_ROW, camera="No Rear Camera")
    out = extract.clean_row(row)
    assert out["camera_main_mp"] == pytest.approx(0.0)
    assert out["camera_rear_count"] == 0


def test_clean_frame_preserves_row_count_and_columns():
    df = pd.DataFrame([NORMAL_ROW, SHIFTED_ROW])
    cleaned = extract.clean_frame(df)
    assert len(cleaned) == 2
    assert list(cleaned.columns) == list(extract.CLEAN_COLUMNS)
    assert cleaned.loc[0, "chip_brand"] == "Snapdragon"
    assert cleaned.loc[1, "battery_mah"] == pytest.approx(1450.0)
