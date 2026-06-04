"""Content-based extraction of one cleaned row from a raw smartphone row.

Each attribute is located by its distinctive signature (``mAh``, ``inches``,
``… MP``, ``inbuilt``/``RAM``, a chip brand or ``Core``/``GHz``, ``Memory
Card``, an OS keyword) scanned across every text column, so column-shifted
feature-phone rows are realigned automatically instead of trusting position.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

import pandas as pd

from . import parsers

NAN = float("nan")

# Cleaned output schema, in display order.
CLEAN_COLUMNS = [
    "model",
    "price",
    "rating",
    "processor_ghz",
    "processor_cores",
    "chip_brand",
    "ram_gb",
    "storage_gb",
    "battery_mah",
    "display_size_in",
    "display_refresh_hz",
    "camera_main_mp",
    "camera_front_mp",
    "camera_rear_count",
    "card_supported",
    "os_family",
]

# Columns scanned (in priority order) when locating an attribute by content.
_SCAN_COLUMNS = ["processor", "ram", "battery", "display", "camera", "card", "os", "sim"]

_DEFAULT_REFRESH_HZ = 60.0  # un-labelled panels are standard 60 Hz, not "missing"


def _sig_battery(cell: str) -> bool:
    return bool(re.search(r"\d\s*mAh", cell, re.IGNORECASE))


def _sig_display(cell: str) -> bool:
    return bool(re.search(r"\d\s*inch", cell, re.IGNORECASE))


def _sig_camera(cell: str) -> bool:
    return bool(re.search(r"\d\s*MP|rear camera|front camera", cell, re.IGNORECASE))


def _sig_memory(cell: str) -> bool:
    return bool(re.search(r"inbuilt|\d\s*(?:GB|MB)\s*RAM", cell, re.IGNORECASE))


def _sig_card(cell: str) -> bool:
    return "memory card" in cell.lower()


def _sig_os(cell: str) -> bool:
    return parsers.parse_os_family(cell) != "Other"


def _sig_processor(cell: str) -> bool:
    if parsers.parse_chip_brand(cell) != "Other":
        return True
    return bool(re.search(r"core|GHz|MHz|Processor", cell, re.IGNORECASE))


def _find_cell(row: Mapping[str, object], signature) -> str:
    """First normalised cell (across scan columns) matching ``signature``."""
    for col in _SCAN_COLUMNS:
        if col not in row:
            continue
        cell = parsers.normalize_ws(row[col])
        if cell and signature(cell):
            return cell
    return ""


def clean_row(row: Mapping[str, object]) -> dict[str, object]:
    """Decompose one raw row into the structured :data:`CLEAN_COLUMNS` schema."""
    processor = _find_cell(row, _sig_processor)
    memory = _find_cell(row, _sig_memory)
    battery = _find_cell(row, _sig_battery)
    display = _find_cell(row, _sig_display)
    camera = _find_cell(row, _sig_camera)
    card = _find_cell(row, _sig_card)
    os_cell = _find_cell(row, _sig_os)

    refresh = parsers.parse_display_refresh_hz(display)
    if math.isnan(refresh) and display:
        refresh = _DEFAULT_REFRESH_HZ

    main_mp = parsers.parse_camera_main_mp(camera)
    rear_count = parsers.parse_camera_rear_count(camera) if camera else 0
    if math.isnan(main_mp) and "no rear camera" in camera.lower():
        main_mp = 0.0

    card_value = parsers.parse_card_supported(card)
    card_supported = "Yes" if card_value == 1.0 else "No"

    return {
        "model": parsers.normalize_ws(row.get("model")),
        "price": parsers.parse_price(row.get("price")),
        "rating": parsers._first_number(parsers.normalize_ws(row.get("rating"))),
        "processor_ghz": parsers.parse_processor_ghz(processor),
        "processor_cores": parsers.parse_cores(processor),
        "chip_brand": parsers.parse_chip_brand(processor),
        "ram_gb": parsers.parse_ram_gb(memory),
        "storage_gb": parsers.parse_storage_gb(memory),
        "battery_mah": parsers.parse_battery_mah(battery),
        "display_size_in": parsers.parse_display_size_in(display),
        "display_refresh_hz": refresh,
        "camera_main_mp": main_mp,
        "camera_front_mp": parsers.parse_camera_front_mp(camera),
        "camera_rear_count": rear_count,
        "card_supported": card_supported,
        "os_family": parsers.parse_os_family(os_cell),
    }


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Apply :func:`clean_row` to every row, returning the cleaned frame."""
    cleaned = [clean_row(record) for record in df.to_dict(orient="records")]
    return pd.DataFrame(cleaned, columns=CLEAN_COLUMNS)
