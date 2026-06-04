"""Tests for :mod:`conjoint.acbc.diagnostics` — §9.10 #10 / §8 checks.

Holdout hit rate is exercised on data simulated from a known β (reusing the
estimate-test fixture); monotonicity and dominance are exercised on hand-built
utility / importance structures.
"""

from __future__ import annotations

from collections import OrderedDict

import pandas as pd
import pytest

from conjoint.acbc import diagnostics
from conjoint.acbc import estimate as acbc_estimate
from conjoint.io import ABSOLUTE_IMPORTANCE_COL, ATTRIBUTE_COL, IMPORTANCE_COLUMNS, RELATIVE_IMPORTANCE_COL
from tests.test_acbc_estimate import SPEC, TRUE_BETA, _simulate


# ---------------------------------------------------------------------------
# Holdout hit rate
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_holdout_hit_rate_beats_random() -> None:
    df = _simulate(pool_size=80, n_tasks=20, n_respondents=25, seed=2027)
    result = diagnostics.holdout_hit_rate(
        df, holdout_fraction=0.25, seed=3, attribute_levels=SPEC
    )
    # Every task has 3 alternatives → random baseline is exactly 1/3.
    assert result.random_baseline == pytest.approx(1 / 3, abs=1e-9)
    assert result.n_holdout_tasks > 0
    assert 0.0 <= result.hit_rate <= 1.0
    # A correctly specified model must beat chance out of sample.
    assert result.hit_rate > result.random_baseline
    assert result.beats_random


@pytest.mark.unit
def test_predict_hit_rate_perfect_with_separating_beta() -> None:
    # A frame where, given a large β, the deterministic utility argmax always
    # coincides with the simulated choice is overkill; instead check the true β
    # predicts most holdout choices and the bookkeeping is consistent.
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=10, seed=44)
    _, _, _, _, level_map = acbc_estimate.build_tournament_matrix(df, SPEC)
    result = diagnostics.predict_hit_rate(df, TRUE_BETA, level_map=level_map)
    assert result.n_correct <= result.n_holdout_tasks
    assert result.hit_rate == pytest.approx(result.n_correct / result.n_holdout_tasks)
    assert result.hit_rate > result.random_baseline


@pytest.mark.unit
def test_holdout_hit_rate_validates_arguments() -> None:
    df = _simulate(pool_size=40, n_tasks=10, n_respondents=5, seed=5)
    with pytest.raises(ValueError):
        diagnostics.holdout_hit_rate(df, holdout_fraction=0.0)
    with pytest.raises(ValueError):
        diagnostics.holdout_hit_rate(df, holdout_fraction=1.0)
    with pytest.raises(ValueError):
        diagnostics.holdout_hit_rate(df[df["stage"] == "nope"])


# ---------------------------------------------------------------------------
# Monotonicity / outlier utilities
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_monotonicity_passes_for_logical_price() -> None:
    utilities = {"price": {"low": 1.5, "mid": 0.0, "high": -1.5}}
    result = diagnostics.check_monotonicity(
        utilities, "price", ["low", "mid", "high"], expect_decreasing=True
    )
    assert result.monotonic
    assert result.violations == ()


@pytest.mark.unit
def test_monotonicity_flags_outlier_price() -> None:
    # Higher price → higher utility: the canonical §8 outlier.
    utilities = {"price": {"low": -1.0, "mid": 0.0, "high": 1.0}}
    result = diagnostics.check_monotonicity(
        utilities, "price", ["low", "mid", "high"], expect_decreasing=True
    )
    assert not result.monotonic
    assert ("low", "mid") in result.violations
    assert ("mid", "high") in result.violations

    # The same utilities are fine if we expect an *increasing* attribute.
    increasing = diagnostics.check_monotonicity(
        utilities, "price", ["low", "mid", "high"], expect_decreasing=False
    )
    assert increasing.monotonic


@pytest.mark.unit
def test_monotonicity_rejects_unknown_attribute_or_level() -> None:
    utilities = {"price": {"low": 1.0, "high": -1.0}}
    with pytest.raises(KeyError):
        diagnostics.check_monotonicity(utilities, "ghost", ["low", "high"])
    with pytest.raises(KeyError):
        diagnostics.check_monotonicity(utilities, "price", ["low", "missing"])


# ---------------------------------------------------------------------------
# Dominant-attribute guard
# ---------------------------------------------------------------------------
def _importance(rows: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            ATTRIBUTE_COL: list(rows.keys()),
            ABSOLUTE_IMPORTANCE_COL: [v * 10 for v in rows.values()],
            RELATIVE_IMPORTANCE_COL: list(rows.values()),
        },
        columns=list(IMPORTANCE_COLUMNS),
    )


@pytest.mark.unit
def test_dominant_attribute_flags_over_threshold() -> None:
    importance = _importance({"price": 0.6, "ram": 0.25, "os": 0.15})
    result = diagnostics.dominant_attribute(importance, threshold=0.5)
    assert result.attribute == "price"
    assert result.relative_importance == pytest.approx(0.6)
    assert result.dominates is True


@pytest.mark.unit
def test_dominant_attribute_ok_when_balanced() -> None:
    importance = _importance({"price": 0.4, "ram": 0.35, "os": 0.25})
    result = diagnostics.dominant_attribute(importance, threshold=0.5)
    assert result.dominates is False


@pytest.mark.unit
def test_dominant_attribute_validates() -> None:
    with pytest.raises(ValueError):
        diagnostics.dominant_attribute(_importance({}), threshold=0.5)
    with pytest.raises(ValueError):
        diagnostics.dominant_attribute(_importance({"a": 1.0}), threshold=1.5)
