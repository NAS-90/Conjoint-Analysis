"""Build ``survey_questions.json`` (Part A + Part C) from a ``Survey_questions`` sheet.

The attribute sections of the survey are generated into ``questionnaire_spec.json``
from a product's feature table. The non-attribute sections — Part A (background
profiling) and Part C (willingness-to-pay) — are *not* product features, so they
are authored in a separate per-product ``Survey_questions`` Excel sheet and
converted here into the ``survey_questions.json`` the survey reads at runtime
(see :mod:`survey_views.section_source`).

Sheet schema (one row per question; blank rows ignored):

==========  ===============================================================
column      meaning
==========  ===============================================================
section     ``A`` (background) / ``C`` (WTP feature) / ``bands`` (amount band)
id          stable identifier / band code (e.g. ``budget``, ``up_to_50``)
prompt      question text (A), upgrade label (C), or band label (bands)
input_type  ``single`` or ``multi`` (Part A only; ignored elsewhere)
options     ``;``-separated choices (Part A only)
help        optional caption (Part A only)
==========  ===============================================================

Run::

    python -m conjoint.generate_survey_questions \\
        --excel "smart phone dataset.xlsx" --out survey_questions.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Union

import pandas as pd

import preprocessing as pp

PathLike = Union[str, Path]

SPEC_VERSION = "0.1"
DEFAULT_SHEET = "Survey_questions"

#: Accepted ``section`` aliases → canonical kind.
_BACKGROUND = {"a", "a_general", "background", "profiling"}
_WTP = {"c", "c_wtp", "wtp", "surcharge"}
_BANDS = {"band", "bands", "amount", "amount_band", "amount_bands"}


def _cell(row: pd.Series, key: str, default: str = "") -> str:
    """Return a trimmed string cell (blank for NaN/None/missing)."""
    value = row.get(key, default)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip()


def build_questions(df: pd.DataFrame) -> dict[str, object]:
    """Convert a ``Survey_questions`` DataFrame into the questions document.

    Validates at the boundary (fail fast with a clear message) and returns a
    new dict; the input is never mutated. Sections that have no rows are simply
    omitted, so the survey falls back to its built-in defaults for them.
    """
    background: list[dict[str, object]] = []
    features: list[dict[str, str]] = []
    bands: list[list[str]] = []
    seen_bg: set[str] = set()
    seen_wtp: set[str] = set()
    seen_band: set[str] = set()

    for _, row in df.iterrows():
        section = _cell(row, "section").lower()
        identifier = _cell(row, "id")
        prompt = _cell(row, "prompt")
        if not section or not identifier:
            continue  # blank / spacer row

        if section in _BACKGROUND:
            options = [o for o in pp.split_semicolon(row.get("options", "")) if o.strip()]
            if not prompt or len(options) < 2:
                raise ValueError(
                    f"background question {identifier!r} needs a prompt and >=2 options"
                )
            if identifier in seen_bg:
                raise ValueError(f"duplicate background id {identifier!r}")
            seen_bg.add(identifier)
            multi = _cell(row, "input_type", "single").lower() == "multi"
            entry: dict[str, object] = {
                "id": identifier,
                "prompt": prompt,
                "input_type": "multi" if multi else "single",
                "options": options,
            }
            help_text = _cell(row, "help")
            if help_text:
                entry["help"] = help_text
            background.append(entry)

        elif section in _WTP:
            if not prompt:
                raise ValueError(f"wtp feature {identifier!r} needs a label (prompt)")
            if identifier in seen_wtp:
                raise ValueError(f"duplicate wtp id {identifier!r}")
            seen_wtp.add(identifier)
            features.append({"id": identifier, "label": prompt})

        elif section in _BANDS:
            if not prompt:
                raise ValueError(f"amount band {identifier!r} needs a label (prompt)")
            if identifier in seen_band:
                raise ValueError(f"duplicate amount band code {identifier!r}")
            seen_band.add(identifier)
            bands.append([identifier, prompt])

        else:
            raise ValueError(
                f"unknown section {section!r} for row {identifier!r} "
                "(use A / C / bands)"
            )

    document: dict[str, object] = {"version": SPEC_VERSION}
    if background:
        document["background"] = background
    wtp: dict[str, object] = {}
    if bands:
        wtp["amount_bands"] = bands
    if features:
        wtp["features"] = features
    if wtp:
        document["wtp"] = wtp
    return document


def build_from_workbook(path: PathLike, sheet: str = DEFAULT_SHEET) -> dict[str, object]:
    """Read the ``Survey_questions`` sheet from ``path`` and build the document."""
    df = pd.read_excel(path, sheet_name=sheet)
    return build_questions(df)


def write_questions(document: dict[str, object], out: PathLike) -> Path:
    """Write ``survey_questions.json`` (pretty-printed, UTF-8). Returns the path."""
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


def main(argv: list[str] | None = None) -> None:
    """CLI: ``Survey_questions`` sheet → ``survey_questions.json``."""
    parser = argparse.ArgumentParser(description="Build survey_questions.json")
    parser.add_argument("--excel", required=True, help="product workbook path")
    parser.add_argument("--sheet", default=DEFAULT_SHEET, help="sheet name")
    parser.add_argument("--out", default="survey_questions.json", help="output JSON path")
    args = parser.parse_args(argv)
    document = build_from_workbook(args.excel, args.sheet)
    path = write_questions(document, args.out)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
