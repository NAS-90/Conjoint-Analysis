"""Generate a folder of *per-respondent* questionnaire CSVs (simulated real people).

Where :mod:`scripts.make_synthetic_survey` writes ONE combined
``acbc_responses.csv``, this writes the *folder of individual*
``responses_<id>.csv`` files a fielded study actually collects — one file per
simulated respondent, byte-for-byte the shape each person downloads from the
survey app's "Send my responses" button (Part A background, B2 deal-breakers,
B4 choices, B5 calibration, Part C WTP). The results dashboard's "Local
responses folder" mode reads exactly this folder.

Choices are utility-driven (:mod:`conjoint.acbc.respondent_sim`), so the people
are heterogeneous and feeding them to Hierarchical Bayes recovers a sensible
importance / part-worth structure. Deterministic given ``--seed``.

Product-agnostic: reads the same env vars as the app — ``SURVEY_SPEC`` (attribute
spec JSON) and ``SURVEY_WORKBOOK`` (Part A/C workbook). With neither set it falls
back to the committed smartphone defaults.

Usage (computer product, as currently running)::

    SURVEY_SPEC=questionnaire_spec_computers.json \
    SURVEY_WORKBOOK=computer_survey_questions.xlsx \
        .venv/bin/python scripts/make_survey_responses.py --n 50 --seed 2026
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
from conjoint.acbc.responses import RESPONDENT_COL, RESPONSES_FILE_PREFIX  # noqa: E402
from survey_views import section_source as ss  # noqa: E402

DEFAULT_N = 50
DEFAULT_SEED = 2026
DEFAULT_PREFIX = "P"


def _spec_path() -> Path:
    return Path(os.environ.get("SURVEY_SPEC") or ROOT / "questionnaire_spec.json")


def _output_dir(spec_path: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    stem = spec_path.stem.replace("questionnaire_spec", "").strip("_") or "default"
    return ROOT / "outputs" / f"survey_responses_{stem}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="number of respondents (one CSV each)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="deterministic seed")
    parser.add_argument("--out", default=None, help="output folder (defaults to outputs/survey_responses_<product>)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="respondent id prefix (default 'P' → P001, P002, …)")
    return parser.parse_args()


def _clear_existing(out_dir: Path) -> int:
    """Remove any prior ``responses_*.csv`` so the folder reflects only this run."""
    removed = 0
    for stale in out_dir.glob(f"{RESPONSES_FILE_PREFIX}*.csv"):
        stale.unlink()
        removed += 1
    return removed


def main() -> None:
    args = _parse_args()
    if args.n <= 0:
        raise SystemExit(f"--n must be positive (got {args.n})")

    spec_path = _spec_path()
    workbook = os.environ.get("SURVEY_WORKBOOK")

    spec = q.read_spec(spec_path)
    attribute_levels = attribute_levels_from_spec(spec)
    questions = ss.load_background_questions(workbook)
    features = ss.load_wtp_features(workbook)
    bands = ss.load_amount_bands(workbook)
    feature_attribute = rs.default_wtp_feature_attribute(features, attribute_levels)

    frame, _pop, _truths = rs.generate_synthetic_responses(
        spec,
        questions=questions,
        wtp_features=features,
        amount_bands=bands,
        wtp_feature_attribute=feature_attribute,
        n_respondents=args.n,
        seed=args.seed,
        respondent_prefix=args.prefix,
    )

    errors = R.validate_acbc_responses(frame, attribute_levels)

    out_dir = _output_dir(spec_path, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    removed = _clear_existing(out_dir)

    # Split the combined frame back into one file per respondent — exactly the
    # artifact the survey app hands each person.
    written: list[Path] = []
    for respondent, person in frame.groupby(RESPONDENT_COL, sort=False):
        path = out_dir / f"{RESPONSES_FILE_PREFIX}{respondent}.csv"
        person.to_csv(path, index=False)
        written.append(path)

    print("# Per-respondent survey questionnaires")
    print(f"  spec        : {spec_path}")
    print(f"  workbook    : {workbook or '(built-in defaults)'}")
    print(f"  respondents : {len(written)}  (seed {args.seed})")
    print(f"  attributes  : {', '.join(attribute_levels)}")
    print(f"  validation  : {'OK — no errors' if not errors else errors}")
    if removed:
        print(f"  cleared     : {removed} stale file(s)")
    print(f"  saved to    : {out_dir}/ ({RESPONSES_FILE_PREFIX}*.csv)")
    sample = ", ".join(p.name for p in written[:3])
    if sample:
        print(f"  examples    : {sample}{' …' if len(written) > 3 else ''}")


if __name__ == "__main__":
    main()
