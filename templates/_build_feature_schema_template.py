"""Build feature_schema_template.xlsx from the unified schema.

Run from the Distance-Analysis/ directory:
    python templates/_build_feature_schema_template.py

Produces templates/feature_schema_template.xlsx with two sheets:
- Edited: an empty product table with product_id + three sample feature columns
- Feature_data: the full schema with two filled example rows + one blank row
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation


OUT = Path(__file__).parent / "feature_schema_template.xlsx"


SCHEMA_COLUMNS: list[tuple[str, str]] = [
    ("feature_name", "Required. snake_case, must match a column in Edited."),
    ("description", "Required. Human-readable, shown in dashboard tooltips."),
    ("data_types", "Required. One of: metric, ordinal, binary, nominal, text."),
    ("included_in_analysis", "Required. yes | no. 'no' = excluded from distance + conjoint."),
    ("normalization_method", "Required. z-score | min-max | ordinal-mapping | none."),
    ("ideal_direction", "Required. higher | lower | neutral."),
    ("weight_importance", "Optional fallback weight: high | medium-high | medium | low-medium | low | none."),
    ("unit", "Optional, display only. e.g. hp, mm, mAh, R$, EUR."),
    ("value_min", "Optional sanity check; metric features only."),
    ("value_max", "Optional sanity check; metric features only."),
    ("conjoint_role", "Required for Module 2/3: attribute | identifier | derived | skip."),
    ("conjoint_levels", "Required if conjoint_role=attribute. Semicolon-separated, display order."),
    ("conjoint_level_codes", "Optional. Semicolon-separated codes that map levels to Edited values."),
    ("conjoint_question_type", "Required if conjoint_role=attribute: rating | pairwise | calibration | wtp."),
    ("conjoint_section", "Optional: A_general | B1_rating | B2_importance | B3_pairwise | B4_calibration | C_wtp."),
    ("notes", "Optional free text."),
]


EXAMPLE_ROWS: list[dict[str, object]] = [
    {
        "feature_name": "product_id",
        "description": "Unique product identifier",
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
        "notes": "Required; unique per row in Edited.",
    },
    {
        "feature_name": "transmission_type",
        "description": "Type of transmission",
        "data_types": "nominal",
        "included_in_analysis": "yes",
        "normalization_method": "none",
        "ideal_direction": "neutral",
        "weight_importance": "medium",
        "unit": "",
        "value_min": "",
        "value_max": "",
        "conjoint_role": "attribute",
        "conjoint_levels": "not synchronized; synchronized; powershift; CVT",
        "conjoint_level_codes": "not synchronized; synchronized; powershift; cvt",
        "conjoint_question_type": "rating",
        "conjoint_section": "B1_rating",
        "notes": "N=381 reference utilities: -65.04 / 10.14 / 31.5 / 23.4.",
    },
    {
        "feature_name": "price",
        "description": "Retail price in local currency",
        "data_types": "metric",
        "included_in_analysis": "yes",
        "normalization_method": "z-score",
        "ideal_direction": "lower",
        "weight_importance": "high",
        "unit": "R$",
        "value_min": 1000,
        "value_max": 300000,
        "conjoint_role": "skip",
        "conjoint_levels": "",
        "conjoint_level_codes": "",
        "conjoint_question_type": "",
        "conjoint_section": "",
        "notes": "Cleaned by universal_numeric_cleaner (₹/commas stripped).",
    },
    {key: "" for key, _ in SCHEMA_COLUMNS},  # blank starter row for the user
]


EDITED_SAMPLE = pd.DataFrame(
    [
        {"product_id": "ExampleBrand A | 100hp | basic", "transmission_type": "synchronized", "price": 55000},
        {"product_id": "ExampleBrand A | 120hp | premium", "transmission_type": "CVT", "price": 89000},
        {"product_id": "ExampleBrand B | 90hp | basic", "transmission_type": "not synchronized", "price": 42000},
    ]
)


ENUMS = {
    "data_types": ["metric", "ordinal", "binary", "nominal", "text"],
    "included_in_analysis": ["yes", "no"],
    "normalization_method": ["z-score", "min-max", "ordinal-mapping", "none"],
    "ideal_direction": ["higher", "lower", "neutral"],
    "weight_importance": ["high", "medium-high", "medium", "low-medium", "low", "none"],
    "conjoint_role": ["attribute", "identifier", "derived", "skip"],
    "conjoint_question_type": ["rating", "pairwise", "calibration", "wtp", ""],
    "conjoint_section": [
        "A_general",
        "B1_rating",
        "B2_importance",
        "B3_pairwise",
        "B4_calibration",
        "C_wtp",
        "",
    ],
}


def build() -> None:
    schema_df = pd.DataFrame(EXAMPLE_ROWS, columns=[col for col, _ in SCHEMA_COLUMNS])

    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        EDITED_SAMPLE.to_excel(writer, sheet_name="Edited", index=False)
        schema_df.to_excel(writer, sheet_name="Feature_data", index=False)

    wb = load_workbook(OUT)
    ws = wb["Feature_data"]

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for col_idx, (col, help_text) in enumerate(SCHEMA_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.comment = Comment(help_text, "schema")
        ws.column_dimensions[get_column_letter(col_idx)].width = max(16, min(40, len(col) + 6))

    n_rows = ws.max_row
    extra_validation_rows = 200
    last_row = n_rows + extra_validation_rows

    for col, allowed in ENUMS.items():
        col_idx = next(i for i, (name, _) in enumerate(SCHEMA_COLUMNS, start=1) if name == col)
        letter = get_column_letter(col_idx)
        joined = ",".join(allowed)
        dv = DataValidation(type="list", formula1=f'"{joined}"', allow_blank=True)
        dv.error = f"Must be one of: {joined}"
        dv.errorTitle = f"Invalid {col}"
        dv.add(f"{letter}2:{letter}{last_row}")
        ws.add_data_validation(dv)

    ws_edited = wb["Edited"]
    for col_idx, name in enumerate(EDITED_SAMPLE.columns, start=1):
        cell = ws_edited.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        ws_edited.column_dimensions[get_column_letter(col_idx)].width = max(18, len(name) + 6)

    wb.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
