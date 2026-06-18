"""Generate ONE fully-completed example questionnaire (any product).

Simulates a single coherent respondent walking the whole linear survey — Part A
background, B2 deal-breakers, B4 pair comparisons, B5 calibration, Part C WTP —
and assembles their answers with the *same* :mod:`conjoint.acbc.responses` code
the live "Thank you" page uses. So the printed CSV is exactly the file a
researcher would receive for one person.

The walk itself is delegated to :mod:`conjoint.acbc.respondent_sim` (the shared,
utility-driven engine used by ``make_synthetic_survey.py`` for the whole sample),
so this script is now just *one* respondent plus a human-readable walkthrough.

Product-agnostic: it reads whatever the survey is configured for via the same
env vars as the app — ``SURVEY_SPEC`` (attribute spec JSON) and
``SURVEY_WORKBOOK`` (Part A/C workbook). With neither set it falls back to the
committed smartphone defaults.

Usage (computer product, as currently running)::

    SURVEY_SPEC=questionnaire_spec_computers.json \
    SURVEY_WORKBOOK=computer_survey_questions.xlsx \
        .venv/bin/python scripts/example_completed_response.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow running as ``python scripts/...`` from anywhere
    sys.path.insert(0, str(ROOT))

from conjoint import questionnaire as q  # noqa: E402
from conjoint.acbc import respondent_sim as rs  # noqa: E402
from conjoint.acbc import responses as R  # noqa: E402
from conjoint.acbc.constraints import anchor_from_ratings  # noqa: E402
from conjoint.acbc.design import attribute_levels_from_spec  # noqa: E402
from survey_views import section_source as ss  # noqa: E402
from survey_views.spec_source import (  # noqa: E402
    attribute_display_name,
    format_level,
    level_label_map,
)

RESPONDENT = "example_respondent"
SEED = 2026


def _spec_path() -> Path:
    return Path(os.environ.get("SURVEY_SPEC") or ROOT / "questionnaire_spec.json")


def _walkthrough(frame, spec, truth, questions, features, bands, labels) -> None:
    """Print a human-readable account of the one simulated respondent."""
    band_label = dict(bands)

    def _rows(stage):
        return frame[frame[R.STAGE_COL] == stage]

    print("## Part A — about you")
    background = _rows("background").set_index(R.ITEM_COL)[R.RESPONSE_VALUE_COL]
    for question in questions:
        if question.identifier in background.index:
            print(f"  - {question.prompt}\n      → {background.loc[question.identifier]}")

    print("\n## B2 — deal-breakers")
    if not truth.must_have and not truth.unacceptable:
        print("  - (no hard constraints this time)")
    for attribute, level in truth.must_have.items():
        print(f"  - MUST have   {attribute_display_name(attribute)}: {format_level(labels, attribute, level)}")
    for attribute, levels in truth.unacceptable.items():
        for level in levels:
            print(f"  - NEVER accept {attribute_display_name(attribute)}: {format_level(labels, attribute, level)}")

    anchor = anchor_from_ratings(
        {}, spec, must_have=truth.must_have, unacceptable=truth.unacceptable
    )
    print("\n## Derived ideal (anchor)")
    for attribute, code in anchor.levels:
        print(f"  - {attribute_display_name(attribute)}: {format_level(labels, attribute, code)}")

    tournament = _rows("tournament")
    n_tasks = tournament[R.TASK_ID_COL].nunique()
    print(f"\n## B4 — compare options ({n_tasks} comparisons, picked by utility)")
    for task_id, block in tournament.groupby(R.TASK_ID_COL):
        chosen = block[block[R.CHOSEN_COL] == 1][R.ALTERNATIVE_INDEX_COL].iloc[0]
        print(f"  - Comparison {task_id}: chose Option {chr(65 + int(chosen))}")

    print("\n## B5 — would you buy it? (0=no … 5=yes)")
    for _, row in _rows("calibration").iterrows():
        print(f"  - Option {int(row[R.TASK_ID_COL])}: {int(row[R.RESPONSE_VALUE_COL])}/5")

    print("\n## Part C — paying extra")
    wtp = _rows("wtp").set_index(R.ITEM_COL)[R.RESPONSE_VALUE_COL]
    for feature in features:
        if feature.identifier in wtp.index:
            code = wtp.loc[feature.identifier]
            print(f"  - {feature.label}\n      → {band_label.get(code, code)}")


def main() -> None:
    spec_path = _spec_path()
    workbook = os.environ.get("SURVEY_WORKBOOK")
    spec = q.read_spec(spec_path)
    attribute_levels = attribute_levels_from_spec(spec)
    labels = level_label_map(spec)
    active = spec.active_attributes

    questions = ss.load_background_questions(workbook)
    features = ss.load_wtp_features(workbook)
    bands = ss.load_amount_bands(workbook)
    feature_attribute = rs.default_wtp_feature_attribute(features, attribute_levels)

    # One respondent through the shared engine (draw truth → walk the survey).
    pop = rs.population_from_spec(spec)
    rng = np.random.default_rng(SEED)
    truth = rs.draw_respondent_truth(pop, RESPONDENT, rng)
    frame = rs.simulate_respondent(
        truth, spec, pop, rng,
        questions=questions, wtp_features=features, amount_bands=bands,
        wtp_feature_attribute=feature_attribute,
    )
    errors = R.validate_acbc_responses(frame, attribute_levels)

    print("# Example completed questionnaire")
    print(f"  spec     : {spec_path}")
    print(f"  workbook : {workbook or '(built-in defaults)'}")
    print(f"  attributes: {', '.join(a.feature_name for a in active)}\n")
    _walkthrough(frame, spec, truth, questions, features, bands, labels)

    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    stem = spec_path.stem.replace("questionnaire_spec", "").strip("_") or "default"
    out_path = out_dir / f"example_responses_{stem}.csv"
    frame.to_csv(out_path, index=False)

    print(f"\n## responses CSV  ({len(frame)} rows, {len(frame.columns)} cols)")
    print(f"  validation: {'OK — no errors' if not errors else errors}")
    print(f"  saved to  : {out_path}")
    print("\n" + frame.to_string(index=False, max_colwidth=22))


if __name__ == "__main__":
    main()
