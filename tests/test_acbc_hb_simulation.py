"""Tests for HB sampler + share / removal simulation.

These exercise the Phase-4 additions:

* :func:`conjoint.acbc.estimate.fit_hb` recovers a known β population
  on synthetic data and emits sane Rhat statistics.
* :func:`conjoint.acbc.estimate.hb_to_utilities` round-trips the
  effects-coded β back into per-level utilities.
* :func:`conjoint.acbc.simulation.share_of_preference` matches the
  closed-form softmax for hand-crafted inputs.
* :func:`removal_impact` redistributes the removed share among
  survivors (no share is lost or created).
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

from conjoint.acbc import design as acbc_design
from conjoint.acbc import estimate as acbc_estimate
from conjoint.acbc import responses as acbc_responses
from conjoint.acbc import simulation as acbc_simulation
from conjoint.acbc.tournament import build_tasks
from tests.test_acbc_estimate import SPEC, TRUE_BETA  # reuse the synth fixture


def _simulate(
    pool_size: int, n_tasks: int, n_respondents: int, *, seed: int
) -> "pd.DataFrame":
    """Generate Tournament responses from ``TRUE_BETA`` (copied from estimate tests)."""
    import pandas as pd  # local import — keeps top-level imports light

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


# ---------------------------------------------------------------------------
# HB sampler
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_fit_hb_recovers_population_mean() -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=30, seed=51)
    fit = acbc_estimate.fit_hb(
        df,
        attribute_levels=SPEC,
        n_iter=400,
        burn_in=200,
        thinning=2,
        n_chains=2,
        step_scale=0.4,
        seed=51,
    )

    assert fit.beta_means.shape == (30, len(TRUE_BETA))
    # Loose tolerance: 30 respondents × 20 tasks × 400 MCMC iterations is
    # enough to put each component within ~0.6 of truth.
    assert np.allclose(fit.population_mean, TRUE_BETA, atol=0.8), fit.population_mean

    # Rhat near 1.0 for converged chains; allow a generous bound because
    # short chains can have noisy Rhats.
    assert np.all(fit.rhat < 1.6), fit.rhat


@pytest.mark.unit
def test_fit_hb_population_cov_is_positive_definite() -> None:
    """Σ must be the heterogeneity covariance: symmetric, PD, positive diagonal.

    The earlier implementation returned the covariance of the μ *posterior*
    samples, which shrinks toward 0 as the chains converge (and can be
    singular). The fix averages the per-iteration Inverse-Wishart Σ draws.
    """
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=30, seed=61)
    fit = acbc_estimate.fit_hb(
        df, attribute_levels=SPEC,
        n_iter=300, burn_in=150, thinning=2, n_chains=2, seed=61,
    )
    sigma = fit.population_cov
    assert sigma.shape == (len(TRUE_BETA), len(TRUE_BETA))
    # Symmetric.
    assert np.allclose(sigma, sigma.T, atol=1e-8)
    # Positive diagonal (real per-feature heterogeneity variance).
    assert np.all(np.diag(sigma) > 0), np.diag(sigma)
    # Positive-definite ⇒ Cholesky succeeds and all eigenvalues are > 0.
    np.linalg.cholesky(sigma)
    assert np.all(np.linalg.eigvalsh(sigma) > 0)


@pytest.mark.unit
def test_per_respondent_rlh_hb_uses_individual_betas() -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=12, seed=67)
    fit = acbc_estimate.fit_hb(
        df, attribute_levels=SPEC,
        n_iter=300, burn_in=150, thinning=2, n_chains=2, seed=67,
    )
    hb_rlh = acbc_estimate.per_respondent_rlh_hb(df, fit)

    assert set(hb_rlh.columns) == {"respondent", "rlh", "n_tasks"}
    assert len(hb_rlh) == 12
    assert (hb_rlh["rlh"] > 0).all() and (hb_rlh["rlh"] <= 1).all()
    # Individual β_i should fit each respondent's own choices at least as well
    # as the shared population β on average (that's the point of HB).
    mnl = acbc_estimate.fit_from_responses(df, SPEC)
    pop_rlh = acbc_estimate.per_respondent_rlh(df, mnl, attribute_levels=SPEC)
    merged = hb_rlh.merge(pop_rlh, on="respondent", suffixes=("_hb", "_pop"))
    assert merged["rlh_hb"].mean() >= merged["rlh_pop"].mean() - 1e-9


@pytest.mark.unit
def test_per_respondent_rlh_hb_empty_without_tournament() -> None:
    import pandas as pd

    fit = acbc_estimate.fit_hb(
        _simulate(pool_size=60, n_tasks=20, n_respondents=6, seed=71),
        attribute_levels=SPEC, n_iter=200, burn_in=100, thinning=2, n_chains=2, seed=71,
    )
    empty = pd.DataFrame(columns=[acbc_responses.STAGE_COL])
    result = acbc_estimate.per_respondent_rlh_hb(empty, fit)
    assert list(result.columns) == ["respondent", "rlh", "n_tasks"]
    assert result.empty


@pytest.mark.unit
def test_hb_to_utilities_round_trip() -> None:
    df = _simulate(pool_size=60, n_tasks=20, n_respondents=8, seed=53)
    fit = acbc_estimate.fit_hb(
        df, attribute_levels=SPEC,
        n_iter=200, burn_in=100, thinning=2, n_chains=2, seed=53,
    )
    utilities = acbc_estimate.hb_to_utilities(fit)
    # respondent + 2 + 3 + 2 = 8 columns.
    assert list(utilities.columns)[0] == "respondent"
    assert len(utilities.columns) == 1 + sum(len(levels) for levels in SPEC.values())
    # Dropped level utility == -Σ surviving for each attribute.
    for _, row in utilities.iterrows():
        for attribute, codes in SPEC.items():
            survivors = sum(float(row[f"{attribute}__{code}"]) for code in codes[:-1])
            dropped = float(row[f"{attribute}__{codes[-1]}"])
            assert pytest.approx(dropped, abs=1e-9) == -survivors


# ---------------------------------------------------------------------------
# Share-of-preference
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_share_of_preference_matches_softmax() -> None:
    utilities = OrderedDict(
        engine=OrderedDict(basic=-0.5, premium=0.5),
        cabin=OrderedDict(open=0.2, closed=-0.2),
    )
    products = OrderedDict(
        A={"engine": "premium", "cabin": "closed"},   # U = 0.5 - 0.2 = 0.3
        B={"engine": "premium", "cabin": "open"},     # U = 0.5 + 0.2 = 0.7
        C={"engine": "basic", "cabin": "open"},       # U = -0.5 + 0.2 = -0.3
    )
    shares = acbc_simulation.share_of_preference(utilities, products, alpha=1.0)

    raw = np.array([0.3, 0.7, -0.3])
    expected = np.exp(raw) / np.exp(raw).sum()
    assert pytest.approx(shares["A"], rel=1e-9) == expected[0]
    assert pytest.approx(shares["B"], rel=1e-9) == expected[1]
    assert pytest.approx(shares["C"], rel=1e-9) == expected[2]
    assert pytest.approx(sum(shares.values()), rel=1e-9) == 1.0


@pytest.mark.unit
def test_randomized_first_choice_approaches_logit() -> None:
    """With many draws, RFC converges to share_of_preference."""
    utilities = OrderedDict(
        engine=OrderedDict(basic=0.0, premium=1.0),
        cabin=OrderedDict(open=0.0, closed=0.5),
    )
    products = OrderedDict(
        A={"engine": "premium", "cabin": "closed"},
        B={"engine": "basic", "cabin": "open"},
    )
    logit = acbc_simulation.share_of_preference(utilities, products, alpha=1.0)
    rfc = acbc_simulation.randomized_first_choice(
        utilities, products, n_draws=20_000, gumbel_scale=1.0, seed=7
    )
    # 20k draws → MC noise of order ~ sqrt(p(1-p)/n) ~ 0.01.
    assert abs(rfc["A"] - logit["A"]) < 0.03
    assert pytest.approx(sum(rfc.values()), rel=1e-9) == 1.0


# ---------------------------------------------------------------------------
# Removal impact
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_removal_impact_conserves_total_share() -> None:
    utilities_a = OrderedDict(
        engine=OrderedDict(basic=-0.5, premium=0.5),
        cabin=OrderedDict(open=0.2, closed=-0.2),
    )
    utilities_b = OrderedDict(
        engine=OrderedDict(basic=0.3, premium=-0.3),
        cabin=OrderedDict(open=-0.1, closed=0.1),
    )
    products = OrderedDict(
        A={"engine": "premium", "cabin": "closed"},
        B={"engine": "premium", "cabin": "open"},
        C={"engine": "basic", "cabin": "open"},
        D={"engine": "basic", "cabin": "closed"},
    )
    impact = acbc_simulation.removal_impact(
        [utilities_a, utilities_b],
        products,
        ["B"],
        model="logit",
        alpha=1.0,
    )

    # Survivors' shares should sum to 1; removed product → after_share = 0.
    after_total = sum(
        share for product_id, share in impact.after_shares.items()
    )
    assert pytest.approx(after_total, rel=1e-9) == 1.0
    assert impact.after_shares["B"] == 0.0 if "B" in impact.after_shares else True

    # The transfer frame includes one row per product with deltas summing to 0.
    assert set(impact.transfer["product"]) == set(products)
    deltas = impact.transfer["delta"].to_numpy()
    assert pytest.approx(float(deltas.sum()), abs=1e-9) == 0.0


@pytest.mark.unit
def test_removal_impact_rejects_unknown_product() -> None:
    utilities = OrderedDict(engine=OrderedDict(basic=0.0, premium=1.0))
    products = OrderedDict(A={"engine": "premium"}, B={"engine": "basic"})
    with pytest.raises(ValueError):
        acbc_simulation.removal_impact(
            [utilities], products, to_remove=["does-not-exist"]
        )
