"""Phase-0 guard tests for the versioned N=381 tractor fixtures.

These lock the published reference numbers (algorithm_spec.md §5) and the
shape/column contract that Module 3 will consume. They skip cleanly when the
fixtures have not been generated (see scripts/export_n381_fixtures.py), so CI
stays green on a fresh checkout without Nicolas's Excel files.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

# algorithm_spec.md §5 — published relative importance (percent) and tolerance.
SPEC_RI_PCT = {
    "engine": 11.43,
    "injection": 11.39,
    "transmission": 18.21,
    "shuttle": 15.54,
    "gears": 15.55,
    "cabin": 11.48,
    "tank": 16.38,
}
TOLERANCE_PP = 0.5

# AllHP "Customer Value" reference for a few levels (algorithm_spec.md §3/§5).
SPEC_POPULATION_UTILITIES = {
    ("engine", "basic"): -30.41,
    ("engine", "premium"): 30.41,
    ("injection", "mechanical"): 16.28,
    ("transmission", "not_synchronized"): -65.04,
    ("transmission", "powershift"): 31.5,
}


@pytest.fixture
def importance(n381_fixture_dir):
    path = n381_fixture_dir / "importance_reference.json"
    if not path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def population_utilities(n381_fixture_dir):
    path = n381_fixture_dir / "population_utilities_reference.json"
    if not path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")
    return json.loads(path.read_text(encoding="utf-8"))


def test_relative_importance_sums_to_one(importance):
    total = sum(v["relative_importance"] for v in importance.values())
    assert abs(total - 1.0) < 1e-9


def test_relative_importance_matches_spec_reference(importance):
    for attribute, expected_pct in SPEC_RI_PCT.items():
        got_pct = importance[attribute]["relative_importance"] * 100
        assert abs(got_pct - expected_pct) <= TOLERANCE_PP, (
            f"{attribute}: {got_pct:.2f}% vs reference {expected_pct}%"
        )


def test_population_utilities_match_allhp(population_utilities):
    for (attribute, level), expected in SPEC_POPULATION_UTILITIES.items():
        got = population_utilities[attribute][level]
        assert abs(got - expected) <= 0.5, (
            f"{attribute}/{level}: {got:.2f} vs reference {expected}"
        )


def test_per_respondent_utilities_shape(n381_fixture_dir):
    path = n381_fixture_dir / "per_respondent_utilities.csv"
    if not path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")
    frame = pd.read_csv(path)
    assert len(frame) == 381
    assert frame.columns[0] == "respondent"
    assert frame.shape[1] == 22  # respondent + 21 (attribute, level) columns
