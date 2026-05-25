"""Export versioned N=381 tractor conjoint fixtures from Nicolas's local Excel.

The reference workbooks are large and live outside the repo
(`../Nicolas_files/`). This script distils them into small, deterministic
CSV/JSON fixtures that the test-suite can depend on. It is intentionally
*not* run in CI — a maintainer runs it once and commits the output under
`tests/fixtures/n381/`.

Key fact about the source data (verified against `Docs/algorithm_spec.md`):
the `raw_data` sheet of `20191110_Conjoint_Evaluation_v2.xlsx` already holds
the *per-respondent part-worth utilities* (the OLS output), not the raw 1-5
ratings. So these fixtures exercise the §4 aggregation pipeline
(d -> AI -> RI and population utilities), which reproduces the published
`evaluation` / `AllHP` numbers exactly.

Usage (from the Distance-Analysis dir):

    .venv/bin/python scripts/export_n381_fixtures.py \
        --nicolas-dir ../Nicolas_files
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

# Canonical attribute -> ordered (raw_data column index, level_code) mapping.
# Column indices are 1-based into the `raw_data` sheet (col 0 = respondent #).
# Level codes are snake_case slugs reused as the `{attribute}__{level}` column
# contract shared with Module 2 (responses.csv) and Module 3 (design matrix).
ATTRIBUTES: dict[str, list[tuple[int, str]]] = {
    "engine": [(1, "basic"), (2, "premium")],
    "injection": [(3, "mechanical"), (4, "electrical")],
    "transmission": [
        (5, "not_synchronized"),
        (6, "synchronized"),
        (7, "powershift"),
        (8, "cvt"),
    ],
    "shuttle": [
        (9, "no_shuttle"),
        (10, "mechanical_shuttle"),
        (11, "hydraulic_shuttle"),
    ],
    "gears": [(12, "g8_9"), (13, "g12"), (14, "g16_18"), (15, "g24_32")],
    "cabin": [(16, "basic"), (17, "high"), (18, "premium")],
    "tank": [(19, "h8"), (20, "h10"), (21, "h12")],
}

# Human-readable level labels (display order matches ATTRIBUTES), straight from
# the AllHP / raw_data headers — handy for the questionnaire (Module 2).
LEVEL_LABELS: dict[str, list[str]] = {
    "engine": ["basic engine", "premium engine"],
    "injection": ["mechanical", "electrical"],
    "transmission": ["not synchronized", "synchronized", "powershift", "CVT"],
    "shuttle": ["no shuttle", "mechanical shuttle", "hydraulic shuttle"],
    "gears": ["8-9", "12", "16-18", "24-32"],
    "cabin": ["basic quality", "high quality", "premium quality"],
    "tank": [
        "capacity for 8 hours of work",
        "capacity for 10 hours of work",
        "capacity for 12 hours of work",
    ],
}


def col_name(attribute: str, level_code: str) -> str:
    return f"{attribute}__{level_code}"


def load_per_respondent_utilities(eval_xlsx: Path) -> pd.DataFrame:
    raw = pd.read_excel(eval_xlsx, sheet_name="raw_data", header=None)
    body = raw.iloc[2:].reset_index(drop=True)  # drop the 2 header rows
    out = pd.DataFrame()
    out["respondent"] = pd.to_numeric(body.iloc[:, 0], errors="coerce").astype(int)
    for attribute, levels in ATTRIBUTES.items():
        for idx, level_code in levels:
            out[col_name(attribute, level_code)] = pd.to_numeric(
                body.iloc[:, idx], errors="coerce"
            )
    return out


def aggregate(utilities: pd.DataFrame) -> tuple[dict, dict]:
    """Reproduce algorithm_spec.md §4 from per-respondent utilities."""
    absolute_importance: dict[str, float] = {}
    population_utilities: dict[str, dict[str, float]] = {}
    for attribute, levels in ATTRIBUTES.items():
        cols = [col_name(attribute, code) for _, code in levels]
        block = utilities[cols]
        spread = block.max(axis=1).abs() + block.min(axis=1).abs()
        absolute_importance[attribute] = float(spread.mean())
        population_utilities[attribute] = {
            code: float(utilities[col_name(attribute, code)].mean())
            for _, code in levels
        }
    total = sum(absolute_importance.values())
    importance = {
        attribute: {
            "absolute_importance": ai,
            "relative_importance": ai / total,
        }
        for attribute, ai in absolute_importance.items()
    }
    return importance, population_utilities


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nicolas-dir", type=Path, default=Path("../Nicolas_files"))
    parser.add_argument(
        "--eval-xlsx",
        type=Path,
        default=None,
        help="Defaults to <nicolas-dir>/20191110_Conjoint_Evaluation_v2.xlsx",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("tests/fixtures/n381")
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    eval_xlsx = args.eval_xlsx or args.nicolas_dir / "20191110_Conjoint_Evaluation_v2.xlsx"
    args.out_dir.mkdir(parents=True, exist_ok=True)

    utilities = load_per_respondent_utilities(eval_xlsx)
    utilities.to_csv(args.out_dir / "per_respondent_utilities.csv", index=False)

    importance, population = aggregate(utilities)
    (args.out_dir / "importance_reference.json").write_text(
        json.dumps(importance, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "population_utilities_reference.json").write_text(
        json.dumps(population, indent=2) + "\n", encoding="utf-8"
    )

    attribute_levels = {
        attribute: [
            {"code": code, "label": label}
            for (_, code), label in zip(levels, LEVEL_LABELS[attribute])
        ]
        for attribute, levels in ATTRIBUTES.items()
    }
    (args.out_dir / "attribute_levels.json").write_text(
        json.dumps(attribute_levels, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "source": str(eval_xlsx),
        "n_respondents": int(len(utilities)),
        "attributes": list(ATTRIBUTES.keys()),
        "files": [
            "per_respondent_utilities.csv",
            "importance_reference.json",
            "population_utilities_reference.json",
            "attribute_levels.json",
        ],
        "note": (
            "raw_data holds post-OLS per-respondent utilities; these fixtures "
            "exercise algorithm_spec.md §4 aggregation, not the §3 OLS step."
        ),
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Wrote {len(utilities)}-respondent fixtures to {args.out_dir}")
    for attribute, info in importance.items():
        print(f"  {attribute:13s} RI={info['relative_importance']:.6f}")


if __name__ == "__main__":
    main()
