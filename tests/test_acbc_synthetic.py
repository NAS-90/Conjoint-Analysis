"""Tests for :mod:`conjoint.acbc.synthetic` — the demo data generator.

Confirms the frame is contract-valid and that each injected pathology is
surfaced by the §8 quality screen (an end-to-end synthetic → estimate →
quality check).
"""

from __future__ import annotations

import pandas as pd
import pytest

from conjoint.acbc import estimate, quality, synthetic
from conjoint.acbc import responses as acbc_responses

# Cohort sizes used by generate_demo_responses defaults (kept in sync here).
N_GOOD, N_STRAIGHT, N_ILLOGICAL, N_INCOMPLETE, N_SPEED = 90, 6, 6, 6, 6


def _kind_of(respondent: str) -> str:
    n = int(respondent[1:])
    if n <= N_GOOD:
        return "good"
    if n <= N_GOOD + N_STRAIGHT:
        return "straightliner"
    if n <= N_GOOD + N_STRAIGHT + N_ILLOGICAL:
        return "illogical"
    if n <= N_GOOD + N_STRAIGHT + N_ILLOGICAL + N_INCOMPLETE:
        return "incomplete"
    return "speeder"


@pytest.mark.unit
def test_generate_demo_responses_is_contract_valid() -> None:
    df = synthetic.generate_demo_responses()
    assert df["respondent"].nunique() == N_GOOD + N_STRAIGHT + N_ILLOGICAL + N_INCOMPLETE + N_SPEED
    assert "duration" in df.columns
    # Long-format schema validates against the demo spec.
    problems = acbc_responses.validate_acbc_responses(df, synthetic.DEMO_SPEC)
    assert problems == [], problems


@pytest.mark.unit
def test_generate_demo_responses_is_reproducible() -> None:
    a = synthetic.generate_demo_responses(seed=7)
    b = synthetic.generate_demo_responses(seed=7)
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.unit
def test_injected_pathologies_are_flagged() -> None:
    df = synthetic.generate_demo_responses()
    mnl = estimate.fit_from_responses(df)
    level_utilities = estimate.beta_to_level_utilities(
        mnl.beta, mnl.column_names, mnl.level_map
    )
    flags = quality.screen_quality(
        df, level_utilities=level_utilities, duration_col="duration"
    ).set_index("respondent")
    flags["kind"] = [_kind_of(r) for r in flags.index]

    def flagged_rate(kind: str, column: str) -> float:
        sub = flags[flags["kind"] == kind]
        return float(sub[column].astype(bool).mean())

    # Each pathology lights up its own check for every injected respondent…
    assert flagged_rate("straightliner", "straightlining") == 1.0
    assert flagged_rate("illogical", "inconsistent_choices") == 1.0
    assert flagged_rate("incomplete", "incomplete") == 1.0
    assert flagged_rate("speeder", "speeding") == 1.0
    # …and the attentive majority is left alone (noise tolerance).
    assert flagged_rate("good", "flagged") == 0.0


@pytest.mark.unit
def test_demo_importance_keeps_price_monotonic() -> None:
    from conjoint.acbc import diagnostics

    df = synthetic.generate_demo_responses()
    mnl = estimate.fit_from_responses(df)
    level_utilities = estimate.beta_to_level_utilities(
        mnl.beta, mnl.column_names, mnl.level_map
    )
    result = diagnostics.check_monotonicity(
        level_utilities, synthetic.PRICE_ATTRIBUTE, synthetic.PRICE_ORDER, expect_decreasing=True
    )
    assert result.monotonic, result.utilities
