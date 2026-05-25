"""Module 3 tests — §3 OLS estimation and §4 aggregation.

The §4 aggregation is validated DIRECTLY against the N=381 reference fixture
(``per_respondent_utilities.csv`` holds post-OLS part-worths), which it
reproduces to machine precision. The §3 OLS step cannot be checked against
N=381 (the raw 1..5 ratings are not published), so it is validated with
synthetic data plus the documented CVA properties: two-level symmetry and a
fully hand-worked tiny case.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conjoint.estimate import (
    aggregate_importance,
    estimate_part_worths,
    estimate_utilities,
    grouping_from_columns,
    levels_from_attribute_levels,
    population_utilities,
)
from conjoint.io import (
    ABSOLUTE_IMPORTANCE_COL,
    ATTRIBUTE_COL,
    IMPORTANCE_COLUMNS,
    RELATIVE_IMPORTANCE_COL,
    RESPONDENT_COL,
    response_column,
)

# algorithm_spec.md §5 — published relative importance (percent).
SPEC_RI_PCT = {
    "engine": 11.43,
    "injection": 11.39,
    "transmission": 18.21,
    "shuttle": 15.54,
    "gears": 15.55,
    "cabin": 11.48,
    "tank": 16.38,
}
TOLERANCE_PP = 0.5  # spec acceptance band
EXACT_PP = 0.05  # fixture is post-OLS, so we should reproduce it far tighter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def n381_utilities(n381_fixture_dir: Path) -> pd.DataFrame:
    path = n381_fixture_dir / "per_respondent_utilities.csv"
    if not path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")
    return pd.read_csv(path)


@pytest.fixture
def n381_attribute_levels(n381_fixture_dir: Path) -> dict:
    path = n381_fixture_dir / "attribute_levels.json"
    if not path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def n381_importance_reference(n381_fixture_dir: Path) -> dict:
    path = n381_fixture_dir / "importance_reference.json"
    if not path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def n381_population_reference(n381_fixture_dir: Path) -> dict:
    path = n381_fixture_dir / "population_utilities_reference.json"
    if not path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# §4 — aggregation against the N=381 reference
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_n381_importance_within_tolerance(
    n381_utilities, n381_attribute_levels, n381_importance_reference
):
    importance = aggregate_importance(n381_utilities, n381_attribute_levels)
    assert list(importance.columns) == list(IMPORTANCE_COLUMNS)

    by_attribute = importance.set_index(ATTRIBUTE_COL)
    for attribute, expected_pct in SPEC_RI_PCT.items():
        got_pct = by_attribute.loc[attribute, RELATIVE_IMPORTANCE_COL] * 100
        # Spec acceptance band (±0.5 pp).
        assert abs(got_pct - expected_pct) <= TOLERANCE_PP, (
            f"{attribute}: {got_pct:.4f}% vs spec {expected_pct}%"
        )
        # The fixture is post-OLS, so we should reproduce the published value
        # essentially exactly (well under 0.05 pp).
        ref_pct = n381_importance_reference[attribute]["relative_importance"] * 100
        assert abs(got_pct - ref_pct) < EXACT_PP, (
            f"{attribute}: {got_pct:.6f}% vs reference {ref_pct:.6f}%"
        )
        ref_ai = n381_importance_reference[attribute]["absolute_importance"]
        assert by_attribute.loc[attribute, ABSOLUTE_IMPORTANCE_COL] == pytest.approx(
            ref_ai, abs=1e-6
        )


@pytest.mark.integration
def test_n381_population_utilities(
    n381_utilities, n381_attribute_levels, n381_population_reference
):
    population = population_utilities(n381_utilities, n381_attribute_levels)
    for attribute, levels in n381_population_reference.items():
        for level_code, expected in levels.items():
            got = population[attribute][level_code]
            assert got == pytest.approx(expected, abs=0.05), (
                f"{attribute}/{level_code}: {got:.6f} vs reference {expected:.6f}"
            )


@pytest.mark.integration
def test_ri_sums_to_one(n381_utilities, n381_attribute_levels):
    importance = aggregate_importance(n381_utilities, n381_attribute_levels)
    assert importance[RELATIVE_IMPORTANCE_COL].sum() == pytest.approx(1.0, abs=1e-12)


@pytest.mark.unit
def test_ri_sums_to_one_synthetic():
    # Holds regardless of the input distribution — pure construction property.
    levels = {"a": ["a0", "a1"], "b": ["b0", "b1", "b2"]}
    utilities = pd.DataFrame(
        {
            RESPONDENT_COL: [1, 2, 3],
            "a__a0": [-1.0, -2.0, 0.5],
            "a__a1": [1.0, 2.0, -0.5],
            "b__b0": [-3.0, 1.0, -2.0],
            "b__b1": [0.0, -1.0, 0.0],
            "b__b2": [3.0, 0.0, 2.0],
        }
    )
    importance = aggregate_importance(utilities, levels)
    assert importance[RELATIVE_IMPORTANCE_COL].sum() == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# §3 — OLS per respondent (synthetic + properties)
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_two_level_symmetric_utilities():
    # A two-level attribute must yield symmetric ±u (basic = -premium),
    # exactly as the reference shows (Engine: basic -30.41 / premium +30.41).
    grouping = {"engine": ["basic", "premium"]}
    ratings = {"engine__basic": 2, "engine__premium": 5}
    part_worths = estimate_part_worths(ratings, grouping, recode=True)
    basic = part_worths["engine"]["basic"]
    premium = part_worths["engine"]["premium"]
    assert basic == pytest.approx(-premium, abs=1e-12)
    assert premium > basic  # the higher-rated level has the higher utility
    # Recode never changes the result (zero-centering removes the constant).
    part_worths_raw = estimate_part_worths(ratings, grouping, recode=False)
    assert part_worths_raw["engine"]["basic"] == pytest.approx(basic, abs=1e-12)
    assert part_worths_raw["engine"]["premium"] == pytest.approx(premium, abs=1e-12)


@pytest.mark.unit
def test_two_level_symmetry_holds_in_multi_attribute_design():
    # Symmetry of two-level attributes must survive in a wider design (the bug
    # a single shared intercept would introduce). engine + cabin together.
    grouping = OrderedDict(
        [("engine", ["basic", "premium"]), ("cabin", ["basic", "high", "premium"])]
    )
    ratings = {
        "engine__basic": 1,
        "engine__premium": 5,
        "cabin__basic": 2,
        "cabin__high": 3,
        "cabin__premium": 4,
    }
    part_worths = estimate_part_worths(ratings, grouping, recode=True)
    assert part_worths["engine"]["basic"] == pytest.approx(
        -part_worths["engine"]["premium"], abs=1e-12
    )
    # Every attribute is zero-centered.
    for levels in part_worths.values():
        assert sum(levels.values()) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_ols_hand_computed_case():
    # Fully hand-worked tiny example proving the design-matrix / drop-first /
    # recenter recipe (algorithm_spec.md §3).
    #
    # One attribute "engine" with two levels {basic, premium}, one respondent.
    #   Ratings (1..5): basic = 2, premium = 4.
    #   Recode 1..5 -> -2..+2 (subtract 3):  basic = -1, premium = +1.
    #
    #   Design matrix, drop first level (basic). Surviving column: [premium].
    #   With an explicit intercept column:
    #       row(basic)   = [1, 0]   y = -1
    #       row(premium) = [1, 1]   y = +1
    #   Two equations, two unknowns (alpha, beta_premium):
    #       alpha            = -1
    #       alpha + beta_pre = +1   ->  beta_premium = 2
    #
    #   Reconstruct dropped level at 0, add intercept/K (K = 1 attribute):
    #       basic   = 0 + (-1) = -1
    #       premium = 2 + (-1) = +1
    #   Zero-center (mean of [-1, +1] is 0, no change):
    #       basic = -1, premium = +1.
    grouping = {"engine": ["basic", "premium"]}
    ratings = {"engine__basic": 2, "engine__premium": 4}
    part_worths = estimate_part_worths(ratings, grouping, recode=True)
    assert part_worths["engine"]["basic"] == pytest.approx(-1.0, abs=1e-12)
    assert part_worths["engine"]["premium"] == pytest.approx(1.0, abs=1e-12)


@pytest.mark.unit
def test_ols_three_level_hand_computed_case():
    # Three-level single-attribute check. Ratings recoded to -2, 0, +2.
    #   drop L0; design rows [1,0,0],[1,1,0],[1,0,1] ; y = [-2, 0, 2]
    #   alpha = -2 ; beta1 = 2 ; beta2 = 4
    #   add alpha/K (K=1): L0 = -2, L1 = 0, L2 = 2 ; mean 0 -> unchanged.
    grouping = {"gears": ["g8_9", "g12", "g16_18"]}
    ratings = {"gears__g8_9": 1, "gears__g12": 3, "gears__g16_18": 5}
    part_worths = estimate_part_worths(ratings, grouping, recode=True)
    assert part_worths["gears"]["g8_9"] == pytest.approx(-2.0, abs=1e-12)
    assert part_worths["gears"]["g12"] == pytest.approx(0.0, abs=1e-12)
    assert part_worths["gears"]["g16_18"] == pytest.approx(2.0, abs=1e-12)


@pytest.mark.unit
def test_estimate_utilities_dataframe_shape_and_order():
    grouping = OrderedDict(
        [("engine", ["basic", "premium"]), ("tank", ["h8", "h10", "h12"])]
    )
    responses = pd.DataFrame(
        {
            RESPONDENT_COL: [1, 2],
            "engine__basic": [2, 1],
            "engine__premium": [4, 5],
            "tank__h8": [1, 2],
            "tank__h10": [3, 3],
            "tank__h12": [5, 4],
        }
    )
    utilities = estimate_utilities(responses, grouping, recode=True)
    expected_columns = [
        RESPONDENT_COL,
        "engine__basic",
        "engine__premium",
        "tank__h8",
        "tank__h10",
        "tank__h12",
    ]
    assert list(utilities.columns) == expected_columns
    assert len(utilities) == 2
    # Each attribute is zero-centered for every respondent.
    for _, row in utilities.iterrows():
        assert row["engine__basic"] + row["engine__premium"] == pytest.approx(0.0, abs=1e-12)
        assert (
            row["tank__h8"] + row["tank__h10"] + row["tank__h12"]
        ) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_estimate_then_aggregate_roundtrip_synthetic():
    # Build synthetic ratings where one attribute clearly dominates, then check
    # the full §3 -> §4 pipeline ranks it highest.
    rng = np.random.default_rng(0)
    grouping = OrderedDict(
        [("strong", ["lo", "hi"]), ("weak", ["lo", "hi"])]
    )
    records = []
    for respondent in range(1, 51):
        records.append(
            {
                RESPONDENT_COL: respondent,
                "strong__lo": 1,
                "strong__hi": 5,  # large spread -> high importance
                "weak__lo": int(rng.integers(2, 4)),
                "weak__hi": int(rng.integers(3, 5)),  # small spread
            }
        )
    responses = pd.DataFrame.from_records(records)
    utilities = estimate_utilities(responses, grouping, recode=True)
    importance = aggregate_importance(utilities, grouping)
    by_attribute = importance.set_index(ATTRIBUTE_COL)[RELATIVE_IMPORTANCE_COL]
    assert by_attribute["strong"] > by_attribute["weak"]
    assert importance[RELATIVE_IMPORTANCE_COL].sum() == pytest.approx(1.0, abs=1e-12)


@pytest.mark.unit
def test_grouping_inferred_from_columns_when_no_mapping():
    # When no attribute_levels mapping is passed, grouping is derived from the
    # utility columns via conjoint.io.split_response_column.
    utilities = pd.DataFrame(
        {
            RESPONDENT_COL: [1, 2],
            response_column("engine", "basic"): [-1.0, -2.0],
            response_column("engine", "premium"): [1.0, 2.0],
        }
    )
    importance = aggregate_importance(utilities)  # no mapping
    assert list(importance[ATTRIBUTE_COL]) == ["engine"]
    assert importance[RELATIVE_IMPORTANCE_COL].iloc[0] == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Validation / edge cases
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_levels_from_attribute_levels_validates_input():
    with pytest.raises(ValueError):
        levels_from_attribute_levels(["not", "a", "mapping"])
    with pytest.raises(ValueError):
        levels_from_attribute_levels({"engine": []})  # no levels
    with pytest.raises(ValueError):
        levels_from_attribute_levels({"engine": [{"code": ""}]})  # empty code


@pytest.mark.unit
def test_grouping_from_columns_skips_non_level_columns():
    grouping = grouping_from_columns(
        [RESPONDENT_COL, "engine__basic", "engine__premium", "metadata"]
    )
    assert grouping == OrderedDict([("engine", ["basic", "premium"])])
    with pytest.raises(ValueError):
        grouping_from_columns([RESPONDENT_COL, "no_separator_here"])


@pytest.mark.unit
def test_estimate_part_worths_requires_attributes_and_ratings():
    with pytest.raises(ValueError):
        estimate_part_worths({}, {})  # no attributes
    with pytest.raises(KeyError):
        estimate_part_worths({}, {"engine": ["basic", "premium"]})  # missing ratings


@pytest.mark.unit
def test_estimate_part_worths_handles_missing_rating_via_lstsq():
    # A NaN rating for one level is filled by least-squares from the rest;
    # estimation still succeeds and stays zero-centered.
    grouping = {"gears": ["g8_9", "g12", "g16_18"]}
    ratings = {"gears__g8_9": 1, "gears__g12": float("nan"), "gears__g16_18": 5}
    part_worths = estimate_part_worths(ratings, grouping, recode=True)
    assert sum(part_worths["gears"].values()) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.unit
def test_aggregate_importance_rejects_zero_spread():
    # All-equal utilities -> zero spread everywhere -> total AI is 0.
    utilities = pd.DataFrame(
        {RESPONDENT_COL: [1, 2], "engine__basic": [0.0, 0.0], "engine__premium": [0.0, 0.0]}
    )
    with pytest.raises(ValueError):
        aggregate_importance(utilities, {"engine": ["basic", "premium"]})


@pytest.mark.unit
def test_aggregate_importance_reports_missing_columns():
    utilities = pd.DataFrame({RESPONDENT_COL: [1], "engine__basic": [1.0]})
    with pytest.raises(ValueError):
        aggregate_importance(utilities, {"engine": ["basic", "premium"]})


@pytest.mark.unit
def test_estimate_utilities_requires_respondent_column():
    with pytest.raises(ValueError):
        estimate_utilities(pd.DataFrame({"engine__basic": [1]}), {"engine": ["basic"]})


# ---------------------------------------------------------------------------
# CLI smoke test (integration)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_cli_utilities_path_writes_importance(tmp_path, n381_fixture_dir):
    utilities_path = n381_fixture_dir / "per_respondent_utilities.csv"
    levels_path = n381_fixture_dir / "attribute_levels.json"
    if not utilities_path.exists() or not levels_path.exists():
        pytest.skip("N=381 fixtures missing; run scripts/export_n381_fixtures.py")

    from conjoint.estimate import main
    from conjoint.io import read_importance

    out_importance = tmp_path / "importance.csv"
    out_population = tmp_path / "population.json"
    exit_code = main(
        [
            "--utilities",
            str(utilities_path),
            "--attribute-levels",
            str(levels_path),
            "--out-importance",
            str(out_importance),
            "--out-population",
            str(out_population),
        ]
    )
    assert exit_code == 0
    importance = read_importance(out_importance)
    assert list(importance.columns) == list(IMPORTANCE_COLUMNS)
    assert importance[RELATIVE_IMPORTANCE_COL].sum() == pytest.approx(1.0, abs=1e-9)
    population = json.loads(out_population.read_text(encoding="utf-8"))
    assert population["engine"]["basic"] == pytest.approx(-30.412140, abs=0.05)


@pytest.mark.integration
def test_cli_responses_path_runs_ols(tmp_path):
    from conjoint.estimate import main
    from conjoint.io import read_importance, read_utilities

    responses = pd.DataFrame(
        {
            RESPONDENT_COL: [1, 2, 3],
            "engine__basic": [1, 2, 1],
            "engine__premium": [5, 4, 5],
            "tank__h8": [2, 1, 3],
            "tank__h10": [3, 3, 3],
            "tank__h12": [4, 5, 4],
        }
    )
    responses_path = tmp_path / "responses.csv"
    responses.to_csv(responses_path, index=False)

    out_utilities = tmp_path / "utilities.csv"
    out_importance = tmp_path / "importance.csv"
    exit_code = main(
        [
            "--responses",
            str(responses_path),
            "--out-utilities",
            str(out_utilities),
            "--out-importance",
            str(out_importance),
        ]
    )
    assert exit_code == 0
    utilities = read_utilities(out_utilities)
    assert len(utilities) == 3
    # Engine is two-level -> symmetric per respondent.
    assert (utilities["engine__basic"] + utilities["engine__premium"]).abs().max() < 1e-9
    importance = read_importance(out_importance)
    assert importance[RELATIVE_IMPORTANCE_COL].sum() == pytest.approx(1.0, abs=1e-12)
