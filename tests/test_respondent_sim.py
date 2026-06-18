"""Tests for :mod:`conjoint.acbc.respondent_sim` — the multi-respondent simulator.

Covers structural validity (all stages, one chosen per task), determinism
(prefix-stable across N), planted-structure *recovery* via the estimator, and
the constrained / 2-level edge cases.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from conjoint import questionnaire as q
from conjoint.acbc import estimate, respondent_sim as rs
from conjoint.acbc.design import Profile, attribute_levels_from_spec, effects_code
from conjoint.acbc.responses import (
    CHOSEN_COL,
    RESPONDENT_COL,
    STAGE_COL,
    STAGE_TOURNAMENT,
    TASK_ID_COL,
    validate_acbc_responses,
)
from survey_views import section_source as ss

SPEC_PATH = "questionnaire_spec_computers.json"
WORKBOOK = "computer_survey_questions.xlsx"


@pytest.fixture(scope="module")
def banks():
    spec = q.read_spec(SPEC_PATH)
    return (
        spec,
        ss.load_background_questions(WORKBOOK),
        ss.load_wtp_features(WORKBOOK),
        ss.load_amount_bands(WORKBOOK),
    )


def _generate(banks, **kwargs):
    spec, questions, features, bands = banks
    fa = rs.default_wtp_feature_attribute(features, attribute_levels_from_spec(spec))
    return rs.generate_synthetic_responses(
        spec, questions=questions, wtp_features=features, amount_bands=bands,
        wtp_feature_attribute=fa, **kwargs,
    )


@pytest.mark.unit
def test_population_mean_beta_matches_effects_coding(banks) -> None:
    spec = banks[0]
    pop = rs.population_from_spec(spec)
    attribute_levels = attribute_levels_from_spec(spec)

    # column order must match the estimator's effects coder exactly
    dummy = Profile(levels=tuple((a, lv[0]) for a, lv in attribute_levels.items()))
    _, columns, _ = effects_code([dummy], attribute_levels)
    assert tuple(columns) == pop.column_names

    # reconstructed full part-worths sum to zero per attribute (effects coding)
    utilities = estimate.beta_to_level_utilities(pop.mean_beta, pop.column_names, attribute_levels)
    for per_level in utilities.values():
        assert pytest.approx(sum(per_level.values()), abs=1e-9) == 0.0


@pytest.mark.integration
def test_generated_frame_is_valid_and_complete(banks) -> None:
    frame, _, _ = _generate(banks, n_respondents=6, seed=2026)
    attribute_levels = attribute_levels_from_spec(banks[0])

    assert validate_acbc_responses(frame, attribute_levels) == []
    assert frame[RESPONDENT_COL].nunique() == 6
    assert {"background", "musthave", "tournament", "calibration", "wtp"}.issubset(
        set(frame[STAGE_COL].unique())
    )

    # every tournament task records exactly one chosen alternative
    tournament = frame[frame[STAGE_COL] == STAGE_TOURNAMENT]
    chosen = tournament.groupby([RESPONDENT_COL, TASK_ID_COL])[CHOSEN_COL].sum()
    assert (chosen == 1).all()


@pytest.mark.integration
def test_determinism_and_prefix_stability(banks) -> None:
    frame_a, _, _ = _generate(banks, n_respondents=4, seed=99)
    frame_b, _, _ = _generate(banks, n_respondents=4, seed=99)
    pd.testing.assert_frame_equal(frame_a, frame_b)

    # adding a 5th respondent leaves the first four byte-for-byte unchanged
    frame_more, _, _ = _generate(banks, n_respondents=5, seed=99)
    first_four = frame_more[frame_more[RESPONDENT_COL].isin(frame_a[RESPONDENT_COL].unique())]
    pd.testing.assert_frame_equal(
        first_four.reset_index(drop=True), frame_a.reset_index(drop=True)
    )


@pytest.mark.integration
def test_recovers_planted_structure(banks) -> None:
    frame, pop, _ = _generate(banks, n_respondents=150, seed=7)
    mnl = estimate.fit_from_responses(frame)
    importance = estimate.attribute_importance(mnl).set_index("attribute")["relative_importance"]

    planted = pop.part_worth_ranges
    attrs = list(planted)
    rho, _ = spearmanr([planted[a] for a in attrs], [importance[a] for a in attrs])
    assert rho > 0.75  # planted importance ranking is recovered

    # price was planted strictly decreasing and should be among the top drivers
    price = estimate.beta_to_level_utilities(mnl.beta, mnl.column_names, mnl.level_map)["price"]
    assert price["budget"] > price["mid_range"] > price["premium"]
    assert mnl is not None
    assert importance["price"] in set(importance.sort_values(ascending=False).head(3))


@pytest.mark.integration
def test_must_have_constraint_keeps_frame_valid(banks) -> None:
    # Force every respondent to declare a must-have / unacceptable; the frame
    # must still validate (smaller pools just yield fewer tasks).
    frame, _, _ = _generate(banks, n_respondents=5, seed=3, n_tasks=6)
    spec = banks[0]
    # re-run with p_must_have=1 via a manual loop to exercise the constrained path
    pop = rs.population_from_spec(spec)
    questions, features, bands = banks[1], banks[2], banks[3]
    rng = np.random.default_rng(123)
    truth = rs.draw_respondent_truth(pop, "forced", rng, p_must_have=1.0, p_unacceptable=1.0)
    one = rs.simulate_respondent(
        truth, spec, pop, rng, questions=questions, wtp_features=features, amount_bands=bands,
    )
    assert validate_acbc_responses(one, attribute_levels_from_spec(spec)) == []
    assert (one[one[STAGE_COL] == STAGE_TOURNAMENT].groupby(TASK_ID_COL)[CHOSEN_COL].sum() == 1).all()


@pytest.mark.unit
def test_two_level_attribute_is_handled(banks) -> None:
    spec = banks[0]
    pop = rs.population_from_spec(spec)
    # touchscreen has exactly two levels → one surviving effects-coded column
    assert "touchscreen__no_touch" in pop.column_names
    assert pop.part_worth_ranges["touchscreen"] > 0
