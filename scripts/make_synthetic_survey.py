"""Generate a realistic *multi-respondent* ACBC dataset (the survey's output).

Where ``example_completed_response.py`` prints ONE respondent, this script
simulates a whole population of heterogeneous respondents — each walking the
full Part A/B/C questionnaire — and writes the combined long-format
``acbc_responses.csv`` a fielded study would yield. The conjoint analysis and
the results dashboard read this file.

Choices are utility-driven (see :mod:`conjoint.acbc.respondent_sim`), so feeding
the output to Hierarchical Bayes recovers a sensible importance / part-worth
structure. Deterministic given ``--seed``.

Product-agnostic: reads the same env vars as the app — ``SURVEY_SPEC`` (attribute
spec JSON) and ``SURVEY_WORKBOOK`` (Part A/C workbook). With neither set it falls
back to the committed smartphone defaults.

Usage (computer product, as currently running)::

    SURVEY_SPEC=questionnaire_spec_computers.json \
    SURVEY_WORKBOOK=computer_survey_questions.xlsx \
        .venv/bin/python scripts/make_synthetic_survey.py --n 200 --seed 2026
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow running as ``python scripts/...`` from anywhere
    sys.path.insert(0, str(ROOT))

from conjoint import questionnaire as q  # noqa: E402
from conjoint.acbc import responses as R  # noqa: E402
from conjoint.acbc import respondent_sim as rs  # noqa: E402
from conjoint.acbc.design import attribute_levels_from_spec  # noqa: E402
from conjoint.acbc.estimate import attribute_importance, fit_from_responses  # noqa: E402
from survey_views import section_source as ss  # noqa: E402

DEFAULT_N = 200
DEFAULT_SEED = 2026


def _spec_path() -> Path:
    return Path(os.environ.get("SURVEY_SPEC") or ROOT / "questionnaire_spec.json")


def _output_path(spec_path: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    stem = spec_path.stem.replace("questionnaire_spec", "").strip("_") or "default"
    return ROOT / "outputs" / f"synthetic_responses_{stem}.csv"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="number of respondents")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="deterministic seed")
    parser.add_argument("--out", default=None, help="output CSV path (defaults to outputs/...)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    spec_path = _spec_path()
    workbook = os.environ.get("SURVEY_WORKBOOK")

    spec = q.read_spec(spec_path)
    attribute_levels = attribute_levels_from_spec(spec)
    questions = ss.load_background_questions(workbook)
    features = ss.load_wtp_features(workbook)
    bands = ss.load_amount_bands(workbook)
    feature_attribute = rs.default_wtp_feature_attribute(features, attribute_levels)

    frame, pop, truths = rs.generate_synthetic_responses(
        spec,
        questions=questions,
        wtp_features=features,
        amount_bands=bands,
        wtp_feature_attribute=feature_attribute,
        n_respondents=args.n,
        seed=args.seed,
    )

    errors = R.validate_acbc_responses(frame, attribute_levels)
    out_path = _output_path(spec_path, args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_path, index=False)

    # A quick recovered-importance read-out so the operator can sanity-check the
    # simulation without opening the dashboard.
    importance = attribute_importance(fit_from_responses(frame)).set_index("attribute")[
        "relative_importance"
    ]
    top = importance.sort_values(ascending=False).head(3)

    print(f"# Synthetic survey responses")
    print(f"  spec        : {spec_path}")
    print(f"  workbook    : {workbook or '(built-in defaults)'}")
    print(f"  respondents : {args.n}  (seed {args.seed})")
    print(f"  attributes  : {', '.join(attribute_levels)}")
    print(f"  rows x cols : {len(frame)} x {len(frame.columns)}")
    print(f"  validation  : {'OK — no errors' if not errors else errors}")
    print(f"  saved to    : {out_path}")
    print("  recovered top-3 importance:")
    for attribute, value in top.items():
        print(f"    - {attribute}: {value:.1%}")


if __name__ == "__main__":
    main()
