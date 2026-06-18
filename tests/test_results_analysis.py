"""Tests for :mod:`dashboard.results_analysis` — the results read-out core.

The estimation engine is already covered elsewhere; here we test the *new*
stage parsers (WTP, derived WTP, calibration, background) and that the composed
``analyze_survey_results`` bundle drives the market simulator.
"""

from __future__ import annotations

from collections import OrderedDict

import pandas as pd
import pytest

from conjoint import questionnaire as q
from conjoint.acbc import respondent_sim as rs, simulation as sim
from conjoint.acbc.design import attribute_levels_from_spec
from conjoint.acbc.responses import (
    ITEM_COL,
    RESPONDENT_COL,
    RESPONSE_VALUE_COL,
    STAGE_COL,
    STAGE_TOURNAMENT,
)
from dashboard import results_analysis as ra
from survey_views import section_source as ss

SPEC_PATH = "questionnaire_spec_computers.json"
WORKBOOK = "computer_survey_questions.xlsx"


@pytest.fixture(scope="module")
def context():
    spec = q.read_spec(SPEC_PATH)
    questions = ss.load_background_questions(WORKBOOK)
    features = ss.load_wtp_features(WORKBOOK)
    bands = ss.load_amount_bands(WORKBOOK)
    price_labels = {
        level.code: level.label
        for attr in spec.attributes
        if attr.feature_name == "price"
        for level in attr.levels
    }
    fa = rs.default_wtp_feature_attribute(features, attribute_levels_from_spec(spec))
    frame, _, _ = rs.generate_synthetic_responses(
        spec, questions=questions, wtp_features=features, amount_bands=bands,
        wtp_feature_attribute=fa, n_respondents=20, seed=5,
    )
    return spec, bands, price_labels, frame


@pytest.fixture(scope="module")
def results(context):
    _, bands, price_labels, frame = context
    return ra.analyze_survey_results(frame, amount_bands=bands, price_labels=price_labels, hb_iter=150, seed=0)


# --- parse_band_usd ---------------------------------------------------------
@pytest.mark.unit
@pytest.mark.parametrize(
    "label,expected",
    [
        ("Nothing extra", 0.0),
        ("Up to $50 more", 50.0),
        ("Up to $100 more", 100.0),
        ("Up to $250 more", 250.0),
        ("$400 or more", 400.0),
        ("something weird", None),
        ("", None),
    ],
)
def test_parse_band_usd(label, expected) -> None:
    assert ra.parse_band_usd(label) == expected


# --- summarize_wtp / derived WTP -------------------------------------------
@pytest.mark.integration
def test_analyze_bundle_is_complete(results) -> None:
    assert results.wtp is not None
    assert results.calibration is not None
    assert results.background is not None
    assert pytest.approx(results.importance["relative_importance"].sum(), rel=1e-9) == 1.0
    # valued upgrades skew toward paying something
    battery = results.wtp.features["battery"]
    assert battery.share_paid > 0.5


@pytest.mark.integration
def test_hb_utilities_drive_the_simulator(results) -> None:
    util_list = sim.utilities_from_frame(results.hb_utilities, results.level_map)
    assert len(util_list) == results.n_respondents
    products = {
        "A": {a: levels[0] for a, levels in results.level_map.items()},
        "B": {a: levels[-1] for a, levels in results.level_map.items()},
    }
    shares = sim.aggregate_shares([sim.share_of_preference(u, products) for u in util_list])
    assert pytest.approx(sum(shares.values()), rel=1e-9) == 1.0


@pytest.mark.unit
def test_derived_monetary_wtp_available_and_graceful() -> None:
    level_utilities = OrderedDict(
        price=OrderedDict(budget=1.0, mid_range=0.0, premium=-1.0),
        ram=OrderedDict(small=-0.5, large=0.5),
    )
    price_labels = {
        "budget": "Budget (< $600)",
        "mid_range": "Mid-range ($600 – $1 200)",
        "premium": "Premium (> $1 200)",
    }
    derived = ra.derived_monetary_wtp(level_utilities, "price", price_labels)
    assert derived.available and derived.usd_per_util > 0
    assert not derived.per_attribute.empty
    assert set(derived.per_attribute["attribute"]) == {"ram"}  # price excluded

    # no price attribute → graceful, never raises
    no_price = OrderedDict(ram=OrderedDict(small=-0.5, large=0.5))
    fallback = ra.derived_monetary_wtp(no_price, "price", price_labels)
    assert fallback.available is False and fallback.per_attribute is None


# --- calibration / background parsers --------------------------------------
@pytest.mark.unit
def test_summarize_background_splits_multi_answers() -> None:
    df = pd.DataFrame(
        {
            RESPONDENT_COL: ["r1", "r2"],
            STAGE_COL: ["background", "background"],
            ITEM_COL: ["usage", "usage"],
            RESPONSE_VALUE_COL: ["Gaming; Web", "Gaming"],
        }
    )
    summary = ra.summarize_background(df)
    assert summary.questions["usage"]["Gaming"] == 2
    assert summary.questions["usage"]["Web"] == 1


@pytest.mark.unit
def test_summarize_calibration_distribution_sums() -> None:
    df = pd.DataFrame(
        {
            RESPONDENT_COL: ["r1", "r1", "r2"],
            STAGE_COL: ["calibration"] * 3,
            "task_id": [1, 2, 1],
            RESPONSE_VALUE_COL: [5, 3, 0],
        }
    )
    summary = ra.summarize_calibration(df)
    assert sum(summary.distribution.values()) == 3
    assert 0.0 <= summary.mean_probability <= 5.0
    assert summary.distribution[5] == 1 and summary.distribution[0] == 1


@pytest.mark.integration
def test_empty_stages_degrade_gracefully(context) -> None:
    _, bands, price_labels, frame = context
    tournament_only = frame[frame[STAGE_COL] == STAGE_TOURNAMENT].copy()
    res = ra.analyze_survey_results(
        tournament_only, amount_bands=bands, price_labels=price_labels, hb_iter=120, seed=0
    )
    assert res.wtp is None and res.calibration is None and res.background is None
    assert res.n_respondents > 0  # core still populated
