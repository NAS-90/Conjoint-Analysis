"""Assemble the cleaned smartphone workbook (``Edited`` + ``Feature_data``).

The output is a drop-in replacement for the raw workbook: the universal
preprocessor (``preprocessing.py``) consumes it unchanged, but now sees clean
structured numbers instead of noisy composite strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import extract

DATA_SHEET = "Edited"
META_SHEET = "Feature_data"

# (feature_name, data_types, normalization_method, ideal_direction)
# ``model`` is intentionally omitted: it is the product identifier (kept in the
# Edited sheet for labelling, excluded from the analysis/distance math).
_FEATURE_SPEC: tuple[tuple[str, str, str, str], ...] = (
    ("price", "metric", "z-score", "lower"),
    ("rating", "metric", "min-max", "higher"),
    ("processor_ghz", "metric", "min-max", "higher"),
    ("processor_cores", "ordinal", "min-max", "higher"),
    ("chip_brand", "nominal", "none", "neutral"),
    ("ram_gb", "metric", "min-max", "higher"),
    ("storage_gb", "metric", "min-max", "higher"),
    ("battery_mah", "metric", "min-max", "higher"),
    ("display_size_in", "metric", "min-max", "higher"),
    ("display_refresh_hz", "ordinal", "min-max", "higher"),
    ("camera_main_mp", "metric", "min-max", "higher"),
    ("camera_front_mp", "metric", "min-max", "higher"),
    ("camera_rear_count", "ordinal", "min-max", "higher"),
    ("card_supported", "binary", "none", "higher"),
    ("os_family", "nominal", "none", "neutral"),
)


@dataclass(frozen=True)
class CleanReport:
    src_path: Path
    dst_path: Path
    n_rows: int
    n_features: int
    missing_counts: dict[str, int]


def build_feature_data() -> pd.DataFrame:
    """The Feature_data sheet describing every analysed clean column."""
    return pd.DataFrame(
        [
            {
                "feature_name": name,
                "data_types": dtype,
                "included_in_analysis": "yes",
                "normalization_method": norm,
                "ideal_direction": ideal,
            }
            for name, dtype, norm, ideal in _FEATURE_SPEC
        ]
    )


def _missing_counts(cleaned: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column in cleaned.columns:
        if column == "model":
            continue
        counts[column] = int(cleaned[column].isna().sum())
    return counts


def clean_workbook(
    src_path: str | Path,
    dst_path: str | Path,
    data_sheet: str = DATA_SHEET,
) -> CleanReport:
    """Read the raw workbook, clean it, and write the 2-sheet cleaned workbook."""
    src_path = Path(src_path)
    dst_path = Path(dst_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Missing raw workbook: {src_path}")

    raw = pd.read_excel(src_path, sheet_name=data_sheet)
    cleaned = extract.clean_frame(raw)
    feature_data = build_feature_data()

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(dst_path) as writer:
        cleaned.to_excel(writer, sheet_name=DATA_SHEET, index=False)
        feature_data.to_excel(writer, sheet_name=META_SHEET, index=False)

    return CleanReport(
        src_path=src_path,
        dst_path=dst_path,
        n_rows=len(cleaned),
        n_features=len(feature_data),
        missing_counts=_missing_counts(cleaned),
    )
