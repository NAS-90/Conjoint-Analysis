"""Write before/after CSVs so the smartphone cleaning is easy to eyeball.

Produces two files under outputs/smartphones/:
  - cleaned_edited.csv  : the full cleaned structured table (1020 x 16)
  - before_after.csv    : each raw composite string next to the values we
                          extracted from it (same row order, 1020 rows)

Usage:
    python scripts/compare_smartphone_cleaning.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW = Path("smart phone dataset.xlsx")
CLEANED = Path("smart phone dataset (cleaned).xlsx")
OUT_DIR = Path("outputs/smartphones")

# raw column -> cleaned columns derived from it (for the side-by-side view)
PAIRS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("price", ("price",)),
    ("processor", ("chip_brand", "processor_ghz", "processor_cores")),
    ("ram", ("ram_gb", "storage_gb")),
    ("battery", ("battery_mah",)),
    ("display", ("display_size_in", "display_refresh_hz")),
    ("camera", ("camera_main_mp", "camera_front_mp", "camera_rear_count")),
    ("card", ("card_supported",)),
    ("os", ("os_family",)),
)


def main() -> None:
    raw = pd.read_excel(RAW, sheet_name="Edited")
    cleaned = pd.read_excel(CLEANED, sheet_name="Edited")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cleaned.to_csv(OUT_DIR / "cleaned_edited.csv", index=False)

    columns: dict[str, pd.Series] = {"model": cleaned["model"]}
    for raw_col, clean_cols in PAIRS:
        columns[f"RAW_{raw_col}"] = raw[raw_col]
        for clean_col in clean_cols:
            columns[clean_col] = cleaned[clean_col]
    side_by_side = pd.DataFrame(columns)
    side_by_side.to_csv(OUT_DIR / "before_after.csv", index=False)

    print(f"Wrote {OUT_DIR / 'cleaned_edited.csv'}  ({cleaned.shape[0]} x {cleaned.shape[1]})")
    print(f"Wrote {OUT_DIR / 'before_after.csv'}    ({side_by_side.shape[0]} x {side_by_side.shape[1]})")
    print("\nSample — camera string -> structured numbers:")
    sample = side_by_side[["model", "RAW_camera", "camera_main_mp", "camera_front_mp", "camera_rear_count"]]
    print(sample.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
