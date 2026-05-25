"""Generate the authentic conjoint demo workbook (``conjoint_demo.xlsx``).

None of the three shipping datasets (tractors, smartphones, user-upload) carry
conjoint *attributes*, so the dashboard's customer-weighted view has nothing to
show. This script builds a small, honest demo workbook that does:

* ``Edited``       — ~12 tractor configurations, one ``product_id`` per row plus
  the 7 nominal conjoint attributes named exactly ``engine, injection,
  transmission, shuttle, gears, cabin, tank``. Every cell is a level *code*
  drawn from :mod:`tests/fixtures/n381/attribute_levels.json`, and the configs
  collectively cover every level of every attribute, so Module 1's one-hot
  expansion yields ``m_a`` columns that match the published level counts.
* ``Feature_data`` — the unified attribute schema (attribute_schema.md §3): the
  7 attribute rows get ``conjoint_role=attribute`` with their ordered
  ``conjoint_levels`` / ``conjoint_level_codes``, ``conjoint_question_type=rating``
  and ``conjoint_section=B1_rating``; ``product_id`` is the identifier.

The companion ``importance.csv`` is *not* fabricated — it re-uses the real
N=381 study importance via :mod:`scripts.build_demo_importance`.

Usage (from Distance-Analysis/)::

    python scripts/build_demo_workbook.py --out conjoint_demo.xlsx
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEVELS = ROOT / "tests" / "fixtures" / "n381" / "attribute_levels.json"
DEFAULT_OUT = ROOT / "conjoint_demo.xlsx"

DATA_SHEET = "Edited"
META_SHEET = "Feature_data"
IDENTIFIER = "product_id"

#: Attribute order (matches the questionnaire / N=381 importance ordering).
ATTRIBUTES: tuple[str, ...] = (
    "engine",
    "injection",
    "transmission",
    "shuttle",
    "gears",
    "cabin",
    "tank",
)

#: 12 hand-authored tractor configurations as level *codes* per attribute. The
#: set is chosen so (a) every level of every attribute appears at least once —
#: guaranteeing the one-hot ``m_a`` equals the published level count — and (b)
#: the configs span the cheap/basic .. premium spectrum so technical (uniform)
#: and customer-weighted (real RI) neighbours genuinely differ.
CONFIGURATIONS: tuple[dict[str, str], ...] = (
    # product_id, engine, injection, transmission, shuttle, gears, cabin, tank
    {"product_id": "demo_economy", "engine": "basic", "injection": "mechanical",
     "transmission": "not_synchronized", "shuttle": "no_shuttle", "gears": "g8_9",
     "cabin": "basic", "tank": "h8"},
    {"product_id": "demo_economy_plus", "engine": "basic", "injection": "mechanical",
     "transmission": "synchronized", "shuttle": "no_shuttle", "gears": "g8_9",
     "cabin": "basic", "tank": "h8"},
    {"product_id": "demo_utility", "engine": "basic", "injection": "electrical",
     "transmission": "synchronized", "shuttle": "mechanical_shuttle", "gears": "g12",
     "cabin": "basic", "tank": "h10"},
    {"product_id": "demo_utility_hi", "engine": "premium", "injection": "electrical",
     "transmission": "synchronized", "shuttle": "mechanical_shuttle", "gears": "g12",
     "cabin": "high", "tank": "h10"},
    {"product_id": "demo_midrange", "engine": "premium", "injection": "mechanical",
     "transmission": "powershift", "shuttle": "mechanical_shuttle", "gears": "g16_18",
     "cabin": "high", "tank": "h10"},
    {"product_id": "demo_midrange_cvt", "engine": "premium", "injection": "electrical",
     "transmission": "cvt", "shuttle": "mechanical_shuttle", "gears": "g16_18",
     "cabin": "high", "tank": "h12"},
    {"product_id": "demo_field", "engine": "premium", "injection": "electrical",
     "transmission": "powershift", "shuttle": "hydraulic_shuttle", "gears": "g16_18",
     "cabin": "high", "tank": "h12"},
    {"product_id": "demo_field_pro", "engine": "premium", "injection": "electrical",
     "transmission": "powershift", "shuttle": "hydraulic_shuttle", "gears": "g24_32",
     "cabin": "premium", "tank": "h12"},
    {"product_id": "demo_premium", "engine": "premium", "injection": "electrical",
     "transmission": "cvt", "shuttle": "hydraulic_shuttle", "gears": "g24_32",
     "cabin": "premium", "tank": "h12"},
    {"product_id": "demo_premium_alt", "engine": "premium", "injection": "electrical",
     "transmission": "cvt", "shuttle": "hydraulic_shuttle", "gears": "g24_32",
     "cabin": "premium", "tank": "h10"},
    {"product_id": "demo_orchard", "engine": "basic", "injection": "electrical",
     "transmission": "synchronized", "shuttle": "hydraulic_shuttle", "gears": "g24_32",
     "cabin": "premium", "tank": "h8"},
    {"product_id": "demo_compact", "engine": "basic", "injection": "mechanical",
     "transmission": "not_synchronized", "shuttle": "mechanical_shuttle", "gears": "g12",
     "cabin": "basic", "tank": "h8"},
)


def load_levels(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read the ordered ``{attribute: [{code, label}, ...]}`` level definitions."""
    levels = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(levels, dict):
        raise ValueError("attribute_levels.json must be a JSON object")
    return levels


def build_edited_sheet() -> pd.DataFrame:
    """Build the ``Edited`` data sheet from :data:`CONFIGURATIONS`."""
    columns = [IDENTIFIER, *ATTRIBUTES]
    return pd.DataFrame(list(CONFIGURATIONS), columns=columns)


def _semicolon(values: list[str]) -> str:
    return "; ".join(values)


def build_feature_data_sheet(levels: dict[str, list[dict[str, str]]]) -> pd.DataFrame:
    """Build the ``Feature_data`` metadata sheet (unified schema §3)."""
    rows: list[dict[str, object]] = []

    rows.append(
        {
            "feature_name": IDENTIFIER,
            "description": "Demo tractor configuration identifier",
            "data_types": "text",
            "included_in_analysis": "no",
            "normalization_method": "none",
            "ideal_direction": "neutral",
            "weight_importance": "none",
            "unit": "",
            "value_min": "",
            "value_max": "",
            "conjoint_role": "identifier",
            "conjoint_levels": "",
            "conjoint_level_codes": "",
            "conjoint_question_type": "",
            "conjoint_section": "",
            "notes": "Row label only; excluded from distance + conjoint math.",
        }
    )

    for attribute in ATTRIBUTES:
        if attribute not in levels:
            raise ValueError(f"attribute_levels.json is missing attribute '{attribute}'")
        attr_levels = levels[attribute]
        label_list = [str(lv["label"]) for lv in attr_levels]
        code_list = [str(lv["code"]) for lv in attr_levels]
        rows.append(
            {
                "feature_name": attribute,
                "description": f"Tractor {attribute} configuration",
                "data_types": "nominal",
                "included_in_analysis": "yes",
                "normalization_method": "none",
                "ideal_direction": "neutral",
                "weight_importance": "none",
                "unit": "",
                "value_min": "",
                "value_max": "",
                "conjoint_role": "attribute",
                "conjoint_levels": _semicolon(label_list),
                "conjoint_level_codes": _semicolon(code_list),
                "conjoint_question_type": "rating",
                "conjoint_section": "B1_rating",
                "notes": "",
            }
        )

    return pd.DataFrame(rows)


def _validate_codes(levels: dict[str, list[dict[str, str]]]) -> None:
    """Fail fast if any configuration cell uses an unknown level code."""
    known = {attr: {str(lv["code"]) for lv in levels[attr]} for attr in ATTRIBUTES}
    for config in CONFIGURATIONS:
        for attr in ATTRIBUTES:
            code = config[attr]
            if code not in known[attr]:
                raise ValueError(
                    f"configuration {config['product_id']!r} uses unknown "
                    f"{attr} code {code!r}; known: {sorted(known[attr])}"
                )
    # Every level must appear at least once so m_a == published level count.
    for attr in ATTRIBUTES:
        used = {config[attr] for config in CONFIGURATIONS}
        missing = known[attr] - used
        if missing:
            raise ValueError(
                f"attribute '{attr}' levels not covered by any config: {sorted(missing)}"
            )


def build(levels_path: Path, out_path: Path) -> Path:
    """Build the demo workbook and write it to ``out_path``. Returns the path."""
    levels = load_levels(levels_path)
    _validate_codes(levels)
    edited = build_edited_sheet()
    feature_data = build_feature_data_sheet(levels)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        edited.to_excel(writer, sheet_name=DATA_SHEET, index=False)
        feature_data.to_excel(writer, sheet_name=META_SHEET, index=False)
    return out_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = build(args.levels, args.out)
    print(f"Wrote demo workbook with {len(CONFIGURATIONS)} configs to {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
