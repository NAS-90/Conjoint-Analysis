"""Ground-truth tests for :mod:`conjoint.acbc.estimate`.

Generates synthetic Tournament data from a known β, fits the MNL via
L-BFGS, and checks that:

* fitted β is close to the true β,
* the log-likelihood scoring rule matches the analytic value,
* RLH is in the expected (0, 1] range,
* the importance frame uses the contract column order and rows match
  what we compute by hand,
* the CLI assembles importance.csv compatible with
  :func:`conjoint.io.read_importance`.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conjoint.acbc import design as acbc_design
from conjoint.acbc import estimate as acbc_estimate
from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.tournament import build_tasks
from conjoint.io import (
    ABSOLUTE_IMPORTANCE_COL,
    ATTRIBUTE_COL,
    IMPORTANCE_COLUMNS,
    RELATIVE_IMPORTANCE_COL,
    read_importance,
)


SPEC = OrderedDict(
    [
        ("engine", ("basic", "premium")),
        ("transmission", ("manual", "auto", "cvt")),
        ("cabin", ("open", "closed")),
    ]
)
TRUE_BETA = np.array(
    [
        -0.8,   # engine: basic vs (-engine_basic = premium)
        -1.2,   # transmission: manual
        +0.4,   # transmission: auto  → cvt = -(manual + auto) = +0.8
        +0.6,   # cabin: open
    ]
)


def _simulate(
    pool_size: int,
    n_tasks: int,
    n_respondents: int,
    *,
    seed: int,
) -> pd.DataFrame:
    """Simulate Tournament responses from ``TRUE_BETA``."""
    rng = np.random.default_rng(seed)
    profiles = acbc_design.generate_profiles(SPEC, n_profiles=pool_size, seed=seed)
    answers: list[acbc_responses.TournamentResponse] = []
    for respondent_index in range(n_respondents):
        tasks = build_tasks(
            profiles, n_tasks=n_tasks, alts_per_task=3, seed=seed + respondent_index + 1
        )
        for task in tasks:
            X, _, _ = acbc_design.effects_code(task.alternatives, SPEC)
            utilities = X @ TRUE_BETA
            # Gumbel noise → softmax draw.
            noise = rng.gumbel(size=utilities.shape)
            chosen = int(np.argmax(utilities + noise))
            answers.append(
                acbc_responses.TournamentResponse(
                    respondent=f"r{respondent_index + 1}",
                    task=task,
                    chosen_index=chosen,
                )
            )
    return acbc_responses.assemble_tournament_responses(answers, SPEC)


@pytest.mark.unit
def test_mnl_recovers_known_beta() -> None:
    df = _simulate(pool_size=120, n_tasks=40, n_respondents=80, seed=2026)
    fit = acbc_estimate.fit_from_responses(df, attribute_levels=SPEC)

    assert fit.converged
    # With 80 * 40 = 3200 tasks the MLE should be within ~0.15 of truth.
    assert np.allclose(fit.beta, TRUE_BETA, atol=0.15), fit.beta
    # LL must be negative and finite.
    assert fit.log_likelihood < 0
    assert np.isfinite(fit.log_likelihood)


@pytest.mark.unit
def test_log_likelihood_matches_recomputed() -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=10, seed=11)
    X, y, groups, columns, level_map = acbc_estimate.build_tournament_matrix(df, SPEC)
    fit = acbc_estimate.fit_mnl(X, y, groups, column_names=columns, level_map=level_map)
    ll = acbc_estimate.mnl_log_likelihood(fit.beta, X, y, groups)
    assert pytest.approx(ll, rel=1e-6) == fit.log_likelihood


@pytest.mark.unit
def test_rlh_in_zero_one() -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=10, seed=17)
    fit = acbc_estimate.fit_from_responses(df, SPEC)
    rlh = acbc_estimate.compute_rlh(fit.log_likelihood, fit.n_tasks)
    assert 0 < rlh <= 1


@pytest.mark.unit
def test_per_respondent_rlh_shapes() -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=12, seed=19)
    fit = acbc_estimate.fit_from_responses(df, SPEC)
    frame = acbc_estimate.per_respondent_rlh(df, fit, attribute_levels=SPEC)
    assert set(frame.columns) == {"respondent", "rlh", "n_tasks"}
    assert len(frame) == 12
    assert (frame["rlh"] > 0).all()


@pytest.mark.unit
def test_filter_by_rlh_drops_low_scorers() -> None:
    frame = pd.DataFrame(
        {"respondent": ["a", "b", "c"], "rlh": [0.6, 0.2, 0.9], "n_tasks": [10, 10, 10]}
    )
    filtered = acbc_estimate.filter_by_rlh(frame, threshold=0.5)
    assert filtered["respondent"].tolist() == ["a", "c"]


@pytest.mark.unit
def test_attribute_importance_columns_and_normalised() -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=40, seed=23)
    fit = acbc_estimate.fit_from_responses(df, SPEC)
    importance = acbc_estimate.attribute_importance(fit)

    # Column order is the contract that compute_distance_matrix relies on.
    assert list(importance.columns) == list(IMPORTANCE_COLUMNS)
    # Relative importance sums to 1 and rows match attribute order.
    assert pytest.approx(importance[RELATIVE_IMPORTANCE_COL].sum(), rel=1e-9) == 1.0
    assert importance[ATTRIBUTE_COL].tolist() == list(SPEC)
    assert (importance[ABSOLUTE_IMPORTANCE_COL] >= 0).all()


@pytest.mark.unit
def test_beta_to_level_utilities_recovers_dropped_level() -> None:
    df = _simulate(pool_size=120, n_tasks=40, n_respondents=80, seed=29)
    fit = acbc_estimate.fit_from_responses(df, SPEC)
    utilities = acbc_estimate.beta_to_level_utilities(
        fit.beta, fit.column_names, fit.level_map
    )

    # Dropped level utility == -Σ surviving.
    for attribute, per_level in utilities.items():
        levels = list(per_level)
        dropped = per_level[levels[-1]]
        survivors = sum(per_level[code] for code in levels[:-1])
        assert pytest.approx(dropped, rel=1e-9, abs=1e-9) == -survivors


# ---------------------------------------------------------------------------
# §9.8 — utility rescaling
# ---------------------------------------------------------------------------
def _toy_utilities() -> "OrderedDict[str, OrderedDict[str, float]]":
    # price range 4, os range 1 → importance ratio 4:1.
    return OrderedDict(
        price=OrderedDict(budget=2.0, mid=0.0, premium=-2.0),
        os=OrderedDict(android=0.5, ios=-0.5),
    )


@pytest.mark.unit
def test_zero_center_utilities_sum_to_zero() -> None:
    shifted = OrderedDict(
        price=OrderedDict(budget=12.0, mid=10.0, premium=8.0),  # mean 10
    )
    centred = acbc_estimate.zero_center_utilities(shifted)
    assert pytest.approx(sum(centred["price"].values()), abs=1e-12) == 0.0
    # Original is not mutated.
    assert shifted["price"]["budget"] == 12.0


@pytest.mark.unit
def test_zero_centered_diffs_mean_range_is_target_and_preserves_importance() -> None:
    rescaled = acbc_estimate.rescale_zero_centered_diffs(_toy_utilities(), target_range=100.0)
    ranges = {attr: max(v.values()) - min(v.values()) for attr, v in rescaled.items()}
    # Mean attribute range == target.
    assert pytest.approx(sum(ranges.values()) / len(ranges), rel=1e-9) == 100.0
    # Relative importance (range ratio) is preserved by the single global factor.
    assert pytest.approx(ranges["price"] / ranges["os"], rel=1e-9) == 4.0


@pytest.mark.unit
def test_normalize_utility_ranges_maps_to_zero_scale_per_attribute() -> None:
    rescaled = acbc_estimate.normalize_utility_ranges(_toy_utilities(), scale=100.0)
    for per_level in rescaled.values():
        assert pytest.approx(min(per_level.values()), abs=1e-12) == 0.0
        assert pytest.approx(max(per_level.values()), abs=1e-12) == 100.0
    # Flat attribute collapses to all-zero rather than dividing by zero.
    flat = OrderedDict(x=OrderedDict(a=1.0, b=1.0))
    assert list(acbc_estimate.normalize_utility_ranges(flat)["x"].values()) == [0.0, 0.0]


@pytest.mark.unit
def test_rescale_utilities_dispatch_and_validation() -> None:
    utils = _toy_utilities()
    assert acbc_estimate.rescale_utilities(
        utils, method=acbc_estimate.RESCALE_NORMALIZED_RANGES
    ) == acbc_estimate.normalize_utility_ranges(utils)
    with pytest.raises(ValueError):
        acbc_estimate.rescale_utilities(utils, method="not-a-method")


@pytest.mark.integration
def test_cli_writes_importance_csv(tmp_path: Path) -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=40, seed=31)
    responses_path = tmp_path / "acbc_responses.csv"
    acbc_responses.write_acbc_responses(df, responses_path)
    importance_path = tmp_path / "importance.csv"

    exit_code = acbc_estimate.main(
        ["--responses", str(responses_path), "--out-importance", str(importance_path)]
    )
    assert exit_code == 0
    assert importance_path.exists()

    frame = read_importance(importance_path)
    assert list(frame.columns) == list(IMPORTANCE_COLUMNS)
    assert pytest.approx(frame[RELATIVE_IMPORTANCE_COL].sum(), rel=1e-9) == 1.0
