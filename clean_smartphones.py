"""CLI: clean the raw smartphone workbook into a structured, analysis-ready one.

Usage:
    python clean_smartphones.py \
        --input "smart phone dataset.xlsx" \
        --output "smart phone dataset (cleaned).xlsx"

The cleaned workbook decomposes noisy composite strings (camera "50 MP + 8 MP +
2 MP …", display "6.7 inches, 1440 x 3216 px, 120 Hz …") into structured numeric
features and realigns column-shifted feature-phone rows. Feed the cleaned file
to ``preprocessing.py`` / ``compute_distance_matrix.py`` in place of the raw one.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

from smartphone_cleaning.clean import clean_workbook

DEFAULT_INPUT = "smart phone dataset.xlsx"
DEFAULT_OUTPUT = "smart phone dataset (cleaned).xlsx"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean the smartphone workbook.")
    parser.add_argument("--input", type=Path, default=Path(DEFAULT_INPUT))
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--data-sheet", default="Edited")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    report = clean_workbook(args.input, args.output, data_sheet=args.data_sheet)

    print("Smartphone cleaning complete.")
    print(f"Input:  {report.src_path}")
    print(f"Output: {report.dst_path} (rows={report.n_rows}, features={report.n_features})")
    flagged = {k: v for k, v in report.missing_counts.items() if v}
    if flagged:
        print("Unparsed / missing values imputed downstream:")
        for column, count in sorted(flagged.items(), key=lambda kv: -kv[1]):
            print(f"  - {column}: {count}")


if __name__ == "__main__":
    main()
