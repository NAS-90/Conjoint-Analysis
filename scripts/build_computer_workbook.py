"""Generate the **computer / laptop** questionnaire data tables.

This is the laptop counterpart of the smartphone questionnaire. It mirrors the
exact data shapes the survey app already reads, so switching the survey from
phones to computers needs **no code or flow change** — only different Excel data
(plus a regenerated ``questionnaire_spec.json``).

Two artifacts are written (both pure data — same schema as the shipping files):

* ``computer dataset.xlsx`` — a single self-contained workbook with three sheets:

  * ``Edited``          — ~12 laptop configurations, one ``product_id`` per row
    plus the conjoint attribute columns. Every cell is a level *code* and the
    configs collectively cover every level of every attribute (so Module 1's
    one-hot expansion is complete). Same shape as ``conjoint_demo.xlsx``.
  * ``Feature_data``    — the unified attribute schema: each attribute row gets
    ``conjoint_role=attribute`` with ordered ``conjoint_levels`` /
    ``conjoint_level_codes``, ``conjoint_question_type=rating`` and
    ``conjoint_section=B1_rating``. Feeds
    ``python -m conjoint.generate_questionnaire`` → ``questionnaire_spec.json``
    (drives sections B0/B2/B4/B5).
  * ``Survey_questions`` — Part A (background), amount ``bands`` and Part C
    (willingness-to-pay), read **directly at runtime** by
    :mod:`survey_views.section_source`. Same shape as ``survey_questions.xlsx``.

* ``computer_survey_questions.xlsx`` — the ``Survey_questions`` sheet on its own,
  an exact drop-in replacement for ``survey_questions.xlsx`` (point the
  ``SURVEY_WORKBOOK`` env var at it, or rename it over the default).

Usage (from Distance-Analysis/)::

    python scripts/build_computer_workbook.py
    python -m conjoint.generate_questionnaire \
        --excel "computer dataset.xlsx" --out questionnaire_spec_computers.json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK_OUT = ROOT / "computer dataset.xlsx"
DEFAULT_QUESTIONS_OUT = ROOT / "computer_survey_questions.xlsx"

DATA_SHEET = "Edited"
META_SHEET = "Feature_data"
SURVEY_SHEET = "Survey_questions"
IDENTIFIER = "product_id"


# ---------------------------------------------------------------------------
# Conjoint attributes (sections B0/B2/B4/B5) — laptop equivalents of the phone
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Level:
    """One selectable level of an attribute (code stored, label shown)."""

    code: str
    label: str


@dataclass(frozen=True)
class Attribute:
    """One conjoint attribute and its ordered levels."""

    name: str
    description: str
    levels: tuple[Level, ...]


ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        "price",
        "Retail price tier",
        (
            Level("budget", "Budget (< $600)"),
            Level("mid_range", "Mid-range ($600 – $1 200)"),
            Level("premium", "Premium (> $1 200)"),
        ),
    ),
    Attribute(
        "processor",
        "CPU performance tier",
        (
            Level("entry", "Entry (Core i3 / Ryzen 3)"),
            Level("mainstream", "Mainstream (Core i5 / Ryzen 5)"),
            Level("performance", "Performance (Core i7-i9 / Ryzen 7-9)"),
        ),
    ),
    Attribute(
        "ram",
        "System memory",
        (
            Level("8gb", "8 GB"),
            Level("16gb", "16 GB"),
            Level("32gb", "32 GB"),
        ),
    ),
    Attribute(
        "storage",
        "Built-in SSD storage",
        (
            Level("256gb", "256 GB SSD"),
            Level("512gb", "512 GB SSD"),
            Level("1tb", "1 TB SSD"),
        ),
    ),
    Attribute(
        "graphics",
        "Graphics processor",
        (
            Level("integrated", "Integrated graphics"),
            Level("entry_gpu", "Entry dedicated (RTX 3050)"),
            Level("high_gpu", "High-end dedicated (RTX 4070+)"),
        ),
    ),
    Attribute(
        "display",
        "Display size",
        (
            Level("13in", "Compact (13.3 in)"),
            Level("14in", "Standard (14 in)"),
            Level("15in", "Large (15.6 in+)"),
        ),
    ),
    Attribute(
        "battery",
        "Battery life on a charge",
        (
            Level("up_to_8h", "Up to 8 hours"),
            Level("8_12h", "8 – 12 hours"),
            Level("12h_plus", "12 hours+"),
        ),
    ),
    Attribute(
        "os",
        "Operating system",
        (
            Level("windows", "Windows"),
            Level("macos", "macOS"),
            Level("chromeos", "ChromeOS"),
        ),
    ),
    Attribute(
        "touchscreen",
        "Touchscreen support",
        (
            Level("no_touch", "No touchscreen"),
            Level("touch", "Touchscreen"),
        ),
    ),
)


#: 12 hand-authored laptop configurations as level *codes* per attribute. Chosen
#: so every level of every attribute appears at least once (complete one-hot
#: expansion) while spanning the budget .. premium spectrum.
CONFIGURATIONS: tuple[dict[str, str], ...] = (
    {"product_id": "comp_chromebook", "price": "budget", "processor": "entry",
     "ram": "8gb", "storage": "256gb", "graphics": "integrated", "display": "13in",
     "battery": "12h_plus", "os": "chromeos", "touchscreen": "no_touch"},
    {"product_id": "comp_budget_14", "price": "budget", "processor": "entry",
     "ram": "8gb", "storage": "256gb", "graphics": "integrated", "display": "14in",
     "battery": "8_12h", "os": "windows", "touchscreen": "no_touch"},
    {"product_id": "comp_student_2in1", "price": "budget", "processor": "mainstream",
     "ram": "8gb", "storage": "512gb", "graphics": "integrated", "display": "13in",
     "battery": "8_12h", "os": "windows", "touchscreen": "touch"},
    {"product_id": "comp_office_15", "price": "mid_range", "processor": "mainstream",
     "ram": "16gb", "storage": "512gb", "graphics": "integrated", "display": "15in",
     "battery": "8_12h", "os": "windows", "touchscreen": "no_touch"},
    {"product_id": "comp_ultrabook", "price": "mid_range", "processor": "mainstream",
     "ram": "16gb", "storage": "512gb", "graphics": "integrated", "display": "14in",
     "battery": "12h_plus", "os": "windows", "touchscreen": "touch"},
    {"product_id": "comp_macbook_air", "price": "mid_range", "processor": "mainstream",
     "ram": "16gb", "storage": "256gb", "graphics": "integrated", "display": "13in",
     "battery": "12h_plus", "os": "macos", "touchscreen": "no_touch"},
    {"product_id": "comp_creator_14", "price": "mid_range", "processor": "performance",
     "ram": "16gb", "storage": "1tb", "graphics": "entry_gpu", "display": "14in",
     "battery": "8_12h", "os": "windows", "touchscreen": "no_touch"},
    {"product_id": "comp_gaming_entry", "price": "mid_range", "processor": "performance",
     "ram": "16gb", "storage": "512gb", "graphics": "entry_gpu", "display": "15in",
     "battery": "up_to_8h", "os": "windows", "touchscreen": "no_touch"},
    {"product_id": "comp_gaming_pro", "price": "premium", "processor": "performance",
     "ram": "32gb", "storage": "1tb", "graphics": "high_gpu", "display": "15in",
     "battery": "up_to_8h", "os": "windows", "touchscreen": "no_touch"},
    {"product_id": "comp_workstation", "price": "premium", "processor": "performance",
     "ram": "32gb", "storage": "1tb", "graphics": "high_gpu", "display": "15in",
     "battery": "8_12h", "os": "windows", "touchscreen": "touch"},
    {"product_id": "comp_macbook_pro", "price": "premium", "processor": "performance",
     "ram": "32gb", "storage": "1tb", "graphics": "integrated", "display": "14in",
     "battery": "12h_plus", "os": "macos", "touchscreen": "no_touch"},
    {"product_id": "comp_premium_2in1", "price": "premium", "processor": "mainstream",
     "ram": "16gb", "storage": "512gb", "graphics": "entry_gpu", "display": "13in",
     "battery": "up_to_8h", "os": "windows", "touchscreen": "touch"},
)


# ---------------------------------------------------------------------------
# Part A / bands / Part C (read at runtime from the Survey_questions sheet)
# ---------------------------------------------------------------------------
SURVEY_COLUMNS = ("section", "id", "prompt", "input_type", "options", "help")

#: section, id, prompt, input_type, options, help (blank cells -> NaN on write).
SURVEY_ROWS: tuple[dict[str, str], ...] = (
    # --- Part A · About you (background profiling) ---
    {"section": "A", "id": "purchase_timing",
     "prompt": "When are you most likely to buy your next computer?",
     "input_type": "single",
     "options": "Within 3 months; 3–12 months; More than a year; No plans yet"},
    {"section": "A", "id": "current_brand",
     "prompt": "Which brand is your current computer?",
     "input_type": "single",
     "options": "Apple; Dell; HP; Lenovo; ASUS; Acer; Another brand; "
                "I don't have one"},
    {"section": "A", "id": "budget",
     "prompt": "Roughly what budget do you have in mind?",
     "input_type": "single",
     "options": "Under $600; $600 – $1 200; Over $1 200; Not sure yet"},
    {"section": "A", "id": "usage",
     "prompt": "What do you mainly use your computer for?",
     "input_type": "multi",
     "options": "Web & email; Office & productivity; Programming / development; "
                "Gaming; Photo / video editing; Streaming video; School / coursework",
     "help": "Choose all that apply."},
    {"section": "A", "id": "form_factor",
     "prompt": "What type of computer are you looking for?",
     "input_type": "single",
     "options": "Ultraportable laptop; Standard laptop; Gaming laptop; "
                "2-in-1 / convertible; Desktop"},
    {"section": "A", "id": "top_factor",
     "prompt": "What matters most to you when choosing a computer?",
     "input_type": "single",
     "options": "Price; Performance; Battery life; Portability; "
                "Display quality; Brand"},
    # --- Amount bands (shared by Part C) ---
    {"section": "bands", "id": "none", "prompt": "Nothing extra"},
    {"section": "bands", "id": "up_to_100", "prompt": "Up to $100 more"},
    {"section": "bands", "id": "up_to_250", "prompt": "Up to $250 more"},
    {"section": "bands", "id": "400_plus", "prompt": "$400 or more"},
    # --- Part C · Paying extra (willingness-to-pay upgrades) ---
    {"section": "C", "id": "graphics",
     "prompt": "A much more powerful graphics card (RTX 4070+)"},
    {"section": "C", "id": "battery",
     "prompt": "Much longer battery life (12 hours+)"},
    {"section": "C", "id": "memory",
     "prompt": "More memory & storage (32 GB / 1 TB SSD)"},
    {"section": "C", "id": "display",
     "prompt": "A higher-resolution display (4K / OLED)"},
    {"section": "C", "id": "portability",
     "prompt": "A lighter, more portable design (under 1.3 kg)"},
    {"section": "C", "id": "connectivity",
     "prompt": "Thunderbolt 4 / Wi-Fi 6E connectivity"},
)


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------
def build_edited_sheet() -> pd.DataFrame:
    """Build the ``Edited`` data sheet from :data:`CONFIGURATIONS`."""
    columns = [IDENTIFIER, *(attr.name for attr in ATTRIBUTES)]
    return pd.DataFrame(list(CONFIGURATIONS), columns=columns)


def _semicolon(values: tuple[str, ...]) -> str:
    return "; ".join(values)


def build_feature_data_sheet() -> pd.DataFrame:
    """Build the ``Feature_data`` metadata sheet (unified schema)."""
    rows: list[dict[str, object]] = [
        {
            "feature_name": IDENTIFIER,
            "description": "Laptop configuration identifier",
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
    ]
    for attr in ATTRIBUTES:
        rows.append(
            {
                "feature_name": attr.name,
                "description": attr.description,
                "data_types": "nominal",
                "included_in_analysis": "yes",
                "normalization_method": "none",
                "ideal_direction": "neutral",
                "weight_importance": "none",
                "unit": "",
                "value_min": "",
                "value_max": "",
                "conjoint_role": "attribute",
                "conjoint_levels": _semicolon(tuple(lv.label for lv in attr.levels)),
                "conjoint_level_codes": _semicolon(tuple(lv.code for lv in attr.levels)),
                "conjoint_question_type": "rating",
                "conjoint_section": "B1_rating",
                "notes": "",
            }
        )
    return pd.DataFrame(rows)


def build_survey_questions_sheet() -> pd.DataFrame:
    """Build the ``Survey_questions`` sheet (Part A / bands / Part C)."""
    return pd.DataFrame(list(SURVEY_ROWS), columns=list(SURVEY_COLUMNS))


# ---------------------------------------------------------------------------
# Validation (fail fast before writing)
# ---------------------------------------------------------------------------
def _validate_codes() -> None:
    """Fail fast if a config cell uses an unknown code or misses a level."""
    known = {attr.name: {lv.code for lv in attr.levels} for attr in ATTRIBUTES}
    for config in CONFIGURATIONS:
        for attr in ATTRIBUTES:
            code = config[attr.name]
            if code not in known[attr.name]:
                raise ValueError(
                    f"configuration {config['product_id']!r} uses unknown "
                    f"{attr.name} code {code!r}; known: {sorted(known[attr.name])}"
                )
    for attr in ATTRIBUTES:
        used = {config[attr.name] for config in CONFIGURATIONS}
        missing = known[attr.name] - used
        if missing:
            raise ValueError(
                f"attribute {attr.name!r} levels not covered by any config: "
                f"{sorted(missing)}"
            )


# ---------------------------------------------------------------------------
# Build + write
# ---------------------------------------------------------------------------
def build(workbook_out: Path, questions_out: Path) -> tuple[Path, Path]:
    """Write both artifacts. Returns ``(workbook_path, questions_path)``."""
    _validate_codes()
    edited = build_edited_sheet()
    feature_data = build_feature_data_sheet()
    survey_questions = build_survey_questions_sheet()

    workbook_out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(workbook_out, engine="openpyxl") as writer:
        edited.to_excel(writer, sheet_name=DATA_SHEET, index=False)
        feature_data.to_excel(writer, sheet_name=META_SHEET, index=False)
        survey_questions.to_excel(writer, sheet_name=SURVEY_SHEET, index=False)

    questions_out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(questions_out, engine="openpyxl") as writer:
        survey_questions.to_excel(writer, sheet_name=SURVEY_SHEET, index=False)

    return workbook_out, questions_out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook-out", type=Path, default=DEFAULT_WORKBOOK_OUT)
    parser.add_argument("--questions-out", type=Path, default=DEFAULT_QUESTIONS_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workbook, questions = build(args.workbook_out, args.questions_out)
    background = sum(1 for r in SURVEY_ROWS if r["section"] == "A")
    wtp = sum(1 for r in SURVEY_ROWS if r["section"] == "C")
    print(
        f"Wrote {workbook} "
        f"({len(CONFIGURATIONS)} configs, {len(ATTRIBUTES)} attributes, "
        f"{background} Part-A + {wtp} Part-C questions)."
    )
    print(f"Wrote {questions} (Survey_questions only — drop-in for SURVEY_WORKBOOK).")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
