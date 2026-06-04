"""Pure parsers that turn one noisy attribute string into structured numbers.

Every function is side-effect free and tolerant of missing input (``None`` /
``NaN`` / empty), returning ``float('nan')`` (numeric fields) or a sentinel
string. The real workbook embeds thin spaces (U+2009) before units and
non-breaking spaces (U+00A0) inside chip names; :func:`normalize_ws` removes
both before any pattern matching.
"""

from __future__ import annotations

import math
import re

NAN = float("nan")

# Unicode spaces seen in the raw data, normalised to a plain ASCII space.
_SPECIAL_SPACES = (" ", " ", " ", " ", " ")


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def normalize_ws(value: object) -> str:
    """Collapse all whitespace (incl. thin/non-breaking spaces) and strip."""
    if _is_missing(value):
        return ""
    text = str(value)
    for ch in _SPECIAL_SPACES:
        text = text.replace(ch, " ")
    return re.sub(r"\s+", " ", text).strip()


def _first_number(text: str) -> float:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else NAN


# --------------------------------------------------------------------------- #
# price / rating
# --------------------------------------------------------------------------- #
def parse_price(value: object) -> float:
    """``'₹54,999.00'`` -> ``54999.0``."""
    text = normalize_ws(value).replace(",", "")
    return _first_number(text) if text else NAN


# --------------------------------------------------------------------------- #
# processor
# --------------------------------------------------------------------------- #
def parse_processor_ghz(value: object) -> float:
    """Clock speed in GHz; ``MHz`` values are converted (``208 MHz`` -> 0.208)."""
    text = normalize_ws(value)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(GHz|MHz)", text, re.IGNORECASE)
    if not match:
        return NAN
    num = float(match.group(1))
    return num / 1000.0 if match.group(2).lower() == "mhz" else num


_CORE_WORDS = {"single": 1, "dual": 2, "quad": 4, "hexa": 6, "octa": 8, "deca": 10}


def parse_cores(value: object) -> float:
    text = normalize_ws(value).lower()
    match = re.search(r"(single|dual|quad|hexa|octa|deca)\s+core", text)
    return float(_CORE_WORDS[match.group(1)]) if match else NAN


def parse_chip_brand(value: object) -> str:
    """Collapse 296 free-text processor strings into a small brand vocabulary."""
    text = normalize_ws(value).lower()
    if not text:
        return "Other"
    if (
        "snapdragon" in text
        or "sanpdragon" in text  # recurring typo in the raw data
        or "qualcomm" in text
        or re.search(r"\bmsm\d", text)
        or "qm215" in text
    ):
        return "Snapdragon"
    if "dimensity" in text:
        return "Dimensity"
    if "helio" in text or re.search(r"\bmt\d", text):
        return "Helio"
    if "exynos" in text:
        return "Exynos"
    if "kirin" in text:
        return "Kirin"
    if "tensor" in text:
        return "Google Tensor"
    if "bionic" in text or "apple" in text or "fusion apl" in text:
        return "Apple"
    if (
        "unisoc" in text
        or "spreadtrum" in text
        or "tiger" in text
        or re.search(r"\bsc\d", text)
        or re.search(r"\bt\d{3}\b", text)
    ):
        return "Unisoc"
    return "Other"


# --------------------------------------------------------------------------- #
# memory: RAM + internal storage (MB / TB normalised to GB)
# --------------------------------------------------------------------------- #
def _to_gb(num: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "mb":
        return num / 1024.0
    if unit == "tb":
        return num * 1024.0
    return num


def parse_ram_gb(value: object) -> float:
    text = normalize_ws(value)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB)\s*RAM", text, re.IGNORECASE)
    return _to_gb(float(match.group(1)), match.group(2)) if match else NAN


def parse_storage_gb(value: object) -> float:
    text = normalize_ws(value)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB|TB)\s*inbuilt", text, re.IGNORECASE)
    return _to_gb(float(match.group(1)), match.group(2)) if match else NAN


# --------------------------------------------------------------------------- #
# battery
# --------------------------------------------------------------------------- #
def parse_battery_mah(value: object) -> float:
    text = normalize_ws(value)
    match = re.search(r"(\d+(?:\.\d+)?)\s*mAh", text, re.IGNORECASE)
    return float(match.group(1)) if match else NAN


# --------------------------------------------------------------------------- #
# display
# --------------------------------------------------------------------------- #
def parse_display_size_in(value: object) -> float:
    text = normalize_ws(value)
    match = re.search(r"(\d+(?:\.\d+)?)\s*inch", text, re.IGNORECASE)
    return float(match.group(1)) if match else NAN


def parse_display_refresh_hz(value: object) -> float:
    """Refresh rate if stated; ``NaN`` when absent (caller applies a default)."""
    text = normalize_ws(value)
    match = re.search(r"(\d+(?:\.\d+)?)\s*Hz", text, re.IGNORECASE)
    return float(match.group(1)) if match else NAN


# --------------------------------------------------------------------------- #
# camera: the headline composite-string bug
# --------------------------------------------------------------------------- #
_CAMERA_COUNT_WORDS = {"single": 1, "dual": 2, "triple": 3, "quad": 4, "penta": 5}
_MP = re.compile(r"(\d+(?:\.\d+)?)\s*MP", re.IGNORECASE)


def _split_camera(text: str) -> tuple[str, str]:
    """Split ``rear & front`` into (rear, front); front is '' when single-facing."""
    if "&" in text:
        rear, front = text.split("&", 1)
        return rear, front
    return text, ""


def parse_camera_main_mp(value: object) -> float:
    """Main (first-listed) rear sensor megapixels."""
    rear, _ = _split_camera(normalize_ws(value))
    nums = _MP.findall(rear)
    return float(nums[0]) if nums else NAN


def parse_camera_front_mp(value: object) -> float:
    """First front sensor megapixels; ``NaN`` when there is no front camera."""
    _, front = _split_camera(normalize_ws(value))
    if "front" not in front.lower():
        return NAN
    nums = _MP.findall(front)
    return float(nums[0]) if nums else NAN


def parse_camera_rear_count(value: object) -> int:
    """Number of rear sensors (count word wins, else number of MP tokens)."""
    rear, _ = _split_camera(normalize_ws(value))
    low = rear.lower()
    if "no rear camera" in low:
        return 0
    for word, count in _CAMERA_COUNT_WORDS.items():
        if re.search(rf"\b{word}\s+rear", low):
            return count
    return len(_MP.findall(rear))


# --------------------------------------------------------------------------- #
# memory card
# --------------------------------------------------------------------------- #
def parse_card_supported(value: object) -> float:
    """1 supported (incl. hybrid), 0 not supported, ``NaN`` when unstated."""
    text = normalize_ws(value).lower()
    if "memory card" not in text:
        return NAN
    return 0.0 if "not supported" in text else 1.0


# --------------------------------------------------------------------------- #
# operating system
# --------------------------------------------------------------------------- #
def parse_os_family(value: object) -> str:
    text = normalize_ws(value).lower()
    if "android" in text or "pragati" in text:
        return "Android"
    if "ios" in text:
        return "iOS"
    if "harmony" in text or "hongmeng" in text or "emui" in text:
        return "HarmonyOS"
    if "kai" in text:
        return "KaiOS"
    return "Other"
