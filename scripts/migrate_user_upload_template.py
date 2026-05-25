"""Migrate the user-upload template to the unified attribute schema.

Schema migration (attribute_schema.md §6, "User-upload template"):

* Remove the duplicated header row from ``Feature_data``.
* Add the conjoint columns (``conjoint_role``, ``conjoint_levels``,
  ``conjoint_level_codes``, ``conjoint_question_type``, ``conjoint_section``)
  plus the other optional schema columns as empty placeholders, so users can
  fill them in.

The migration is idempotent: re-running it on an already-migrated workbook is a
no-op. It only touches ``templates/custom_product_template.xlsx`` and preserves
the ``Edited`` sheet untouched (the ``product`` identifier column is handled by
auto-detection downstream, per schema §5).

Usage (from Distance-Analysis/):
    python scripts/migrate_user_upload_template.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "custom_product_template.xlsx"

# Full schema column order (attribute_schema.md §3).
SCHEMA_COLUMNS: tuple[str, ...] = (
    "feature_name",
    "description",
    "data_types",
    "included_in_analysis",
    "normalization_method",
    "ideal_direction",
    "weight_importance",
    "unit",
    "value_min",
    "value_max",
    "conjoint_role",
    "conjoint_levels",
    "conjoint_level_codes",
    "conjoint_question_type",
    "conjoint_section",
    "notes",
)


def _drop_duplicated_header(meta: pd.DataFrame) -> pd.DataFrame:
    """Drop a leading row that merely repeats the column names."""
    if meta.empty:
        return meta
    first = meta.iloc[0]
    looks_like_header = all(
        str(first.get(col, "")).strip().lower() == col for col in ["feature_name"]
    )
    if looks_like_header:
        return meta.iloc[1:].reset_index(drop=True)
    return meta


def _add_schema_placeholders(meta: pd.DataFrame) -> pd.DataFrame:
    """Add any missing schema columns as empty strings, in canonical order."""
    out = meta.copy()
    for col in SCHEMA_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    ordered = [c for c in SCHEMA_COLUMNS if c in out.columns]
    extras = [c for c in out.columns if c not in SCHEMA_COLUMNS]
    return out.loc[:, ordered + extras]


def migrate(path: Path = TEMPLATE) -> bool:
    """Migrate the template in place. Returns True if the file was changed."""
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")

    sheets = {name: pd.read_excel(path, sheet_name=name) for name in pd.ExcelFile(path).sheet_names}
    meta = sheets.get("Feature_data")
    if meta is None:
        raise ValueError("Template is missing the Feature_data sheet")

    before_rows = len(meta)
    before_cols = list(meta.columns)

    meta = _drop_duplicated_header(meta)
    meta = _add_schema_placeholders(meta)

    changed = len(meta) != before_rows or list(meta.columns) != before_cols
    if not changed:
        print(f"{path.name}: already migrated; no changes.")
        return False

    sheets["Feature_data"] = meta
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)

    print(
        f"{path.name}: migrated Feature_data "
        f"(rows {before_rows} -> {len(meta)}, cols {len(before_cols)} -> {len(meta.columns)})."
    )
    return True


if __name__ == "__main__":
    migrate()
