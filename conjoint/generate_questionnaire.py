"""CLI for Module 2 — generate the questionnaire spec from a workbook.

Usage::

    python -m conjoint.generate_questionnaire \
        --excel <workbook.xlsx> \
        --out questionnaire_spec.json \
        [--responses-template responses_template.csv]

Thin wrapper around :mod:`conjoint.questionnaire`; all logic lives there.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from conjoint import questionnaire as q

DEFAULT_SPEC_OUT = "questionnaire_spec.json"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a conjoint questionnaire spec from a workbook's "
            "Feature_data sheet."
        ),
    )
    parser.add_argument(
        "--excel",
        type=Path,
        required=True,
        help="Path to the input workbook (*.xlsx) with an Edited + Feature_data sheet.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(DEFAULT_SPEC_OUT),
        help=f"Where to write the questionnaire spec JSON (default: {DEFAULT_SPEC_OUT}).",
    )
    parser.add_argument(
        "--responses-template",
        type=Path,
        default=None,
        help="Optional path for an empty responses.csv template (respondent + B-1 columns).",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    spec = q.build_questionnaire(args.excel)
    spec_path = q.write_spec(spec, args.out)

    active = spec.active_attributes
    rating_columns = q.response_columns(spec)
    print("Questionnaire spec generated.")
    print(f"Input workbook: {args.excel}")
    print(f"Spec: {spec_path} ({len(spec.attributes)} attribute question(s))")
    print(f"Active Part B-1 rating attributes: {len(active)}")
    print(f"Rating response columns: {len(rating_columns)}")

    if args.responses_template is not None:
        template_path = q.write_responses_template(spec, args.responses_template)
        print(f"Responses template: {template_path}")


if __name__ == "__main__":
    main()
