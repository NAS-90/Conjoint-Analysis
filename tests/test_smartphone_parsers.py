"""Unit tests for the smartphone composite-string parsers (TDD).

These cover the "analytical bottleneck" the project flagged: noisy composite
attribute strings such as ``"50 MP + 8 MP + 2 MP Triple Rear & 16 MP Front
Camera"`` or ``"6.7 inches, 1440 x 3216 px, 120 Hz Display with Punch Hole"``
must be decomposed into clean structured numbers, not fed in verbatim.

Inputs deliberately include the thin space (U+2009) and non-breaking space
(U+00A0) that appear in the real workbook.
"""

from __future__ import annotations

import math

import pytest

from smartphone_cleaning import parsers as P

THIN = " "  # U+2009 thin space used before units in the raw data
NBSP = " "  # U+00A0 non-breaking space inside chip names


def is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)


# --------------------------------------------------------------------------- #
# whitespace normalisation
# --------------------------------------------------------------------------- #
def test_normalize_ws_collapses_special_spaces():
    assert P.normalize_ws(f"Snapdragon{NBSP} 695,{THIN}Octa  Core") == "Snapdragon 695, Octa Core"


def test_normalize_ws_handles_missing():
    assert P.normalize_ws(None) == ""
    assert P.normalize_ws(float("nan")) == ""


# --------------------------------------------------------------------------- #
# price
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("₹54,999.00", 54999.0),
        ("₹1,299.00", 1299.0),
        ("₹4,649.00", 4649.0),
    ],
)
def test_parse_price(raw, expected):
    assert P.parse_price(raw) == pytest.approx(expected)


def test_parse_price_missing():
    assert is_nan(P.parse_price(None))


# --------------------------------------------------------------------------- #
# processor clock + cores + brand
# --------------------------------------------------------------------------- #
def test_processor_ghz_basic():
    assert P.parse_processor_ghz(f"Snapdragon 8 Gen2, Octa Core, 3.2{THIN}GHz Processor") == pytest.approx(3.2)


def test_processor_ghz_megahertz_converted_to_ghz():
    assert P.parse_processor_ghz(f"Single Core, 208{THIN}MHz Processor") == pytest.approx(0.208)
    assert P.parse_processor_ghz(f"SC6531E, 26{THIN}MHz Processor") == pytest.approx(0.026)


def test_processor_ghz_absent():
    assert is_nan(P.parse_processor_ghz("Bionic A16, Hexa Core Processor"))
    assert is_nan(P.parse_processor_ghz("Apple A13"))


@pytest.mark.parametrize(
    "raw,cores",
    [
        ("Octa Core, 2.2 GHz Processor", 8),
        ("Hexa Core, 3.22 GHz Processor", 6),
        ("Quad Core, 1.3 GHz Processor", 4),
        ("Dual Core, 1 GHz Processor", 2),
        ("Single Core, 208 MHz Processor", 1),
    ],
)
def test_parse_cores(raw, cores):
    assert P.parse_cores(raw) == cores


def test_parse_cores_absent():
    assert is_nan(P.parse_cores("Apple A13"))


@pytest.mark.parametrize(
    "raw,brand",
    [
        (f"Snapdragon{NBSP} 695, Octa Core, 2.2 GHz Processor", "Snapdragon"),
        ("Qualcomm Snapdragon 625, Octa Core, 2 GHz Processor", "Snapdragon"),
        ("Sanpdragon 680, Octa Core, 2.4 GHz Processor", "Snapdragon"),  # typo in raw data
        ("Dimensity 1080, Octa Core, 2.6 GHz Processor", "Dimensity"),
        ("Helio G85, Octa Core, 2 GHz Processor", "Helio"),
        ("Exynos 1330, Octa Core, 2.4 GHz Processor", "Exynos"),
        ("Kirin 990, Octa Core, 2.86 GHz Processor", "Kirin"),
        ("Google Tensor G2, Octa Core, 2.85 GHz Processor", "Google Tensor"),
        ("Bionic A15, Hexa Core, 3.22 GHz Processor", "Apple"),
        ("Apple A13", "Apple"),
        ("Unisoc T606, Octa Core, 1.6 GHz Processor", "Unisoc"),
        ("Tiger T610, Octa Core, 1.8 GHz Processor", "Unisoc"),
        ("Spreadtrum SC7731, Quad Core, 1.3 GHz Processor", "Unisoc"),
    ],
)
def test_parse_chip_brand(raw, brand):
    assert P.parse_chip_brand(raw) == brand


def test_parse_chip_brand_unknown_is_other():
    assert P.parse_chip_brand("Some Mystery Chip") == "Other"


# --------------------------------------------------------------------------- #
# memory: RAM + internal storage, MB normalised to GB
# --------------------------------------------------------------------------- #
def test_memory_gb():
    raw = f"12{THIN}GB RAM, 256{THIN}GB inbuilt"
    assert P.parse_ram_gb(raw) == pytest.approx(12.0)
    assert P.parse_storage_gb(raw) == pytest.approx(256.0)


def test_memory_mb_converted_to_gb():
    raw = f"48{THIN}MB RAM, 128{THIN}MB inbuilt"
    assert P.parse_ram_gb(raw) == pytest.approx(48 / 1024)
    assert P.parse_storage_gb(raw) == pytest.approx(128 / 1024)


def test_memory_storage_only():
    assert is_nan(P.parse_ram_gb(f"64{THIN}GB inbuilt"))
    assert P.parse_storage_gb(f"64{THIN}GB inbuilt") == pytest.approx(64.0)


# --------------------------------------------------------------------------- #
# battery
# --------------------------------------------------------------------------- #
def test_battery_mah():
    assert P.parse_battery_mah(f"5000{THIN}mAh Battery with 100W Fast Charging") == pytest.approx(5000)
    assert P.parse_battery_mah(f"800{THIN}mAh Battery") == pytest.approx(800)


def test_battery_absent():
    assert is_nan(P.parse_battery_mah("No Battery info"))


# --------------------------------------------------------------------------- #
# display: size + refresh
# --------------------------------------------------------------------------- #
def test_display_size():
    assert P.parse_display_size_in(f"6.7 inches, 1440{THIN}x{THIN}3216{THIN}px, 120 Hz Display with Punch Hole") == pytest.approx(6.7)
    assert P.parse_display_size_in("2 inches, 128 x 160 px Display") == pytest.approx(2.0)


def test_display_refresh():
    assert P.parse_display_refresh_hz("6.7 inches, 1440 x 3216 px, 120 Hz Display") == pytest.approx(120)


def test_display_refresh_absent_returns_nan():
    # Caller decides the 60 Hz default; the parser only reports what's present.
    assert is_nan(P.parse_display_refresh_hz("6.1 inches, 1170 x 2532 px Display with Small Notch"))


# --------------------------------------------------------------------------- #
# camera: the headline composite-string bug
# --------------------------------------------------------------------------- #
def test_camera_triple_rear_with_front():
    raw = f"50{THIN}MP + 48{THIN}MP + 32{THIN}MP Triple Rear & 16{THIN}MP Front Camera"
    assert P.parse_camera_main_mp(raw) == pytest.approx(50)
    assert P.parse_camera_front_mp(raw) == pytest.approx(16)
    assert P.parse_camera_rear_count(raw) == 3


def test_camera_dual_front_takes_first_front_sensor():
    raw = "50 MP + 48 MP + 32 MP Triple Rear & 32 MP + 32 MP Dual Front Camera"
    assert P.parse_camera_main_mp(raw) == pytest.approx(50)
    assert P.parse_camera_front_mp(raw) == pytest.approx(32)
    assert P.parse_camera_rear_count(raw) == 3


def test_camera_single_rear_no_front():
    raw = "0.3 MP Rear Camera"
    assert P.parse_camera_main_mp(raw) == pytest.approx(0.3)
    assert is_nan(P.parse_camera_front_mp(raw))
    assert P.parse_camera_rear_count(raw) == 1


def test_camera_quad_word_overrides_token_count():
    raw = "48 MP Quad Rear Camera"
    assert P.parse_camera_main_mp(raw) == pytest.approx(48)
    assert P.parse_camera_rear_count(raw) == 4


def test_camera_none():
    assert is_nan(P.parse_camera_main_mp("No Rear Camera"))
    assert P.parse_camera_rear_count("No Rear Camera") == 0


# --------------------------------------------------------------------------- #
# memory card
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Memory Card Supported, upto 1 TB", 1),
        ("Memory Card (Hybrid), upto 256 GB", 1),
        ("Memory Card Not Supported", 0),
    ],
)
def test_card_supported(raw, expected):
    assert P.parse_card_supported(raw) == expected


# --------------------------------------------------------------------------- #
# os family
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,family",
    [
        ("Android v13", "Android"),
        ("Android v9 (Pie)", "Android"),
        ("iOS v16", "iOS"),
        ("HarmonyOS v2.0", "HarmonyOS"),
        ("Hongmeng OS v3.0", "HarmonyOS"),
        ("EMUI v12", "HarmonyOS"),
        ("KAI OS", "KaiOS"),
    ],
)
def test_parse_os_family(raw, family):
    assert P.parse_os_family(raw) == family


def test_parse_os_family_garbage_is_other():
    # Shifted rows leak camera/card strings into the os column.
    assert P.parse_os_family("0.3 MP Rear Camera") == "Other"
    assert P.parse_os_family("No FM Radio") == "Other"
