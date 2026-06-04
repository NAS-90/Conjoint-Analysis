"""Tests for the pure core of :mod:`dashboard.quality_diagnostics`.

The Streamlit ``render_*`` functions are exercised manually; here we test the
``analyze_responses`` analysis core and the ``utilities_long`` helper, which is
where all the logic lives.
"""

from __future__ import annotations

from collections import OrderedDict

import pytest

from conjoint.acbc import synthetic
from dashboard.quality_diagnostics import AcbcAnalysis, analyze_responses, utilities_long


@pytest.mark.unit
def test_utilities_long_is_tidy() -> None:
    utilities = OrderedDict(
        price=OrderedDict(budget=1.0, mid=0.0, premium=-1.0),
        os=OrderedDict(android=0.5, ios=-0.5),
    )
    tidy = utilities_long(utilities)
    assert list(tidy.columns) == ["attribute", "level", "utility"]
    assert len(tidy) == 5  # 3 + 2 levels
    assert set(tidy["attribute"]) == {"price", "os"}


@pytest.mark.integration
def test_analyze_responses_on_demo_data() -> None:
    # Small cohort + short HB keeps the test quick but representative.
    df = synthetic.generate_demo_responses(
        n_good=30, n_straightliner=2, n_illogical=2, n_incomplete=2, n_speeder=2, seed=11
    )
    analysis = analyze_responses(df, hb_iter=200, seed=0)

    assert isinstance(analysis, AcbcAnalysis)
    assert analysis.n_respondents == 38

    # Importance normalises and price is the most important attribute.
    assert pytest.approx(analysis.importance["relative_importance"].sum(), rel=1e-9) == 1.0
    assert analysis.dominance.attribute == "price"
    assert not analysis.dominance.dominates  # ~0.44 < 0.5 threshold

    # Holdout beats the random baseline; price utilities decrease (logical).
    assert analysis.holdout.beats_random
    assert analysis.monotonicity is not None and analysis.monotonicity.monotonic

    # Per-respondent HB RLH for everyone, all valid probabilities.
    assert len(analysis.rlh) == 38
    assert (analysis.rlh["rlh"] > 0).all() and (analysis.rlh["rlh"] <= 1).all()

    # Rescaled part-worths: mean attribute range == 100 (zero-centered diffs).
    ranges = [
        max(v.values()) - min(v.values()) for v in analysis.rescaled_utilities.values()
    ]
    assert pytest.approx(sum(ranges) / len(ranges), rel=1e-9) == 100.0
