# ACBC Conjoint Studio — design spec

This document records what the ACBC implementation in `conjoint/acbc/`
does, what assumptions it makes, and how it maps to the reference
algorithm. It is the authoritative cross-reference between the code,
the unit tests and the requirements brief in `MEMORY.md` (or whichever
reference document is currently in play).

The layout follows the same §1–§10 structure as the reference
algorithm document so each algorithmic decision below can be checked
against its source paragraph.

---

## §1 — Inputs and design constraints

* **Spec source.** `conjoint.questionnaire.QuestionnaireSpec` (loaded by
  `survey_views.spec_source.load_spec`) provides the active Part B-1
  attributes and their ordered levels. Inactive attributes (B2/B3/B4/C)
  are ignored by every ACBC entry point.
* **Profile shape.** A `Profile` is an immutable tuple of
  `(attribute, level_code)` pairs preserving spec order
  (`conjoint.acbc.design.Profile`). The data structure is shared across
  BYO / Screener / Tournament.
* **Prohibitions.** None modelled in this MVP. The schema leaves room
  for them: any future filter only has to reject profiles whose pairs
  hit forbidden combinations.

## §2 — Experimental design

* **Profile pool generation.** `generate_profiles()` draws, for each
  attribute, a balanced shuffle of its levels
  (`_balanced_sequence`). The shuffles are combined column-wise and
  then passed through a 2-opt swap heuristic that strictly reduces
  pairwise level co-occurrence (`_minimise_pairwise_overlap`). The
  result is **level-balanced by construction** (every level appears
  ⌊n/K⌋ or ⌈n/K⌉ times) and approximately **minimal-overlap**.
* **Effects coding.** `effects_code()` emits a K-1 column block per
  attribute. Surviving levels carry `+1` in their own column;
  the **dropped (last) level** carries `-1` across every column of
  its attribute. This matches the Sawtooth ACBC parametrisation and
  lets us recover the dropped β as `-Σ` of the surviving betas in
  `beta_to_level_utilities()`.
* **Diagnostics.** `check_level_balance()` returns per-attribute level
  counts; `level_balance_deviation()` returns the worst spread
  (`max-min` per attribute). `check_orthogonality()` returns the
  maximum absolute off-diagonal of `XᵀX/n`. Tests assert that the
  score stays below 0.5 on a randomly-balanced 48-profile design.

## §3 — MNL log-likelihood + fit

* **Specification.** Standard McFadden MNL with Gumbel-i.i.d. error.
  For each task `t` and alternative `j`,
  `P(j|t) = exp(X_{tj}·β) / Σ_k exp(X_{tk}·β)`; the log-likelihood
  sums `y·logP` across all (respondent, task, alternative) rows.
* **Implementation.** `mnl_log_likelihood()` does the softmax per
  task with a numerically-stable max-subtraction. `fit_mnl()` uses
  `scipy.optimize.minimize(method='L-BFGS-B')` with the analytic
  gradient `Xᵀ(y-p)` so the optimisation converges in O(features²)
  steps even on 30+-feature designs.
* **Verification.** `tests/test_acbc_estimate.py` simulates 80
  respondents × 40 tasks × 3 alts from a known `TRUE_BETA`, fits the
  MLE, and asserts the recovered β matches truth within ±0.15.

## §4 — Hierarchical Bayes

* **Model.** Two-level hierarchical model:

  ```
  β_i ~ Normal(μ, Σ)            # per-respondent betas
  μ   ~ Normal(0, c·I)          # weak prior on the mean (c = prior_cov_scale)
  Σ   ~ Inverse-Wishart(I, n+2) # weak prior on the covariance
  ```

* **Sampling.** `fit_hb()` implements a Metropolis-within-Gibbs scheme
  in pure numpy:
  1. **β_i step (Metropolis).** Random-walk proposal
     `β_i + step_scale · N(0, I)`. Accept under
     `log p(β | data) + log p(β | μ, Σ)`.
  2. **μ step (Gibbs).** Conjugate Normal posterior given the current
     β and Σ.
  3. **Σ step (Gibbs).** Inverse-Wishart with the residual scatter +
     prior identity matrix; samples via Bartlett decomposition.
* **Diagnostics.** Two chains by default; Gelman-Rubin Rhat per
  feature (`_gelman_rubin`). `tests/test_acbc_hb_simulation.py`
  checks recovery (tol 0.8 on synthetic data with N=30 respondents
  and short chains) and `Rhat < 1.6`.

## §5 — Root Likelihood (RLH) diagnostic

* **Definition.** `RLH = exp(LL / n_tasks)` — the geometric mean of
  choice probabilities. Sawtooth uses it to flag inattentive
  respondents (RLH at chance = `1/n_alts`).
* **Code path.** `compute_rlh()` is the scalar formula;
  `per_respondent_rlh()` produces a tidy frame with one row per
  respondent (`respondent, rlh, n_tasks`); `filter_by_rlh(threshold)`
  drops low scorers.

## §6 — Attribute importance

* **Range_A.** For each attribute, take `max U − min U` over the
  reconstructed full-level utilities (`beta_to_level_utilities()`).
* **Relative importance.** `RI_a = Range_a / Σ Range`. The result is
  emitted with **exactly** the column order
  `(attribute, absolute_importance, relative_importance)` defined in
  `conjoint.io.IMPORTANCE_COLUMNS`, so `compute_distance_matrix.py`
  (Module 4) keeps reading the file without any contract change.

## §7 — BYO stage

* **Purpose.** Capture a "preferred level" per attribute. Becomes the
  anchor for the Screener and a soft constraint in §3 once integrated.
* **Implementation.** `conjoint/acbc/byo.py` builds one `ByoQuestion`
  per active attribute; `byo_to_anchor()` returns a `Profile`
  (defaulting to the first level when the answer is missing);
  `byo_to_responses()` emits `ByoResponse` records for the long-format
  CSV.
* **UI.** `survey_views/acbc_byo.py` drives one BYO question per page
  through `survey_views.navigation.render_sequence`.

## §8 — Screener stage

* **Pool generation.** `seed_screener_pool()` starts from the BYO
  anchor and flips 1..`max_changes` attributes to a *different* level.
  Each profile is guaranteed distinct from the anchor; duplicates in
  the pool are rejected via a hashed-tuple set.
* **Yes/No filtering.** `filter_survivors()` keeps Yes-vote profiles.
  `unacceptable_levels()` flags attribute=level pairs that the
  respondent rejected at least `min_rejections` times — the signal
  for must-have / must-avoid information.
* **UI.** `survey_views/acbc_screener.py` shows one profile per page
  with a Yes/No radio. On Finish it stashes survivors (plus the
  anchor) in session state for the Tournament.

## §9 — Tournament stage + market simulation

* **Task assembly.** `build_tasks(pool, n_tasks, alts_per_task)`
  partitions the survivor pool into `n_tasks` choice tasks of
  `alts_per_task` distinct profiles each. Seedable.
* **UI.** `survey_views/acbc_tournament.py` renders one task per page.
  It prefers Screener survivors; a checkbox lets a facilitator force a
  fresh random-balanced pool.
* **Market simulation.** `conjoint/acbc/simulation.py` adds three
  primitives:
  - `share_of_preference(utilities, products, alpha)` — analytic
    logit share.
  - `randomized_first_choice(utilities, products, n_draws,
    gumbel_scale)` — Gumbel-noise Monte-Carlo, matching Sawtooth's
    RFC.
  - `removal_impact(utilities_by_respondent, products, to_remove)` —
    before/after shares + a transfer DataFrame.

## §10 — Distance integration

* The customer-weighted distance code (`compute_distance_matrix.py`)
  consumes `importance.csv` only. Because the ACBC estimator writes
  the same schema as the OLS estimator, dropping the MNL output into
  a dataset's `outputs/.../importance.csv` is enough to switch the
  dashboard to ACBC-driven weights — no contract change required.
* The dashboard's **Product Removal** panel now adds a
  before/after-distance histogram and (when `utilities.csv` exists)
  a share-of-preference transfer table.

---

## Cross-reference table

| Algorithm step                  | Module                                              | Test                                                            |
| ------------------------------- | --------------------------------------------------- | --------------------------------------------------------------- |
| Profile pool                    | `conjoint/acbc/design.py::generate_profiles`        | `tests/test_acbc_design.py::test_generate_profiles_is_level_balanced` |
| Effects coding                  | `conjoint/acbc/design.py::effects_code`             | `tests/test_acbc_design.py::test_effects_code_shape_and_dropped_level` |
| MNL log-likelihood              | `conjoint/acbc/estimate.py::mnl_log_likelihood`     | `tests/test_acbc_estimate.py::test_log_likelihood_matches_recomputed` |
| L-BFGS fit                      | `conjoint/acbc/estimate.py::fit_mnl`                | `tests/test_acbc_estimate.py::test_mnl_recovers_known_beta`            |
| HB sampler                      | `conjoint/acbc/estimate.py::fit_hb`                 | `tests/test_acbc_hb_simulation.py::test_fit_hb_recovers_population_mean` |
| RLH                             | `conjoint/acbc/estimate.py::compute_rlh`            | `tests/test_acbc_estimate.py::test_rlh_in_zero_one`                    |
| Attribute importance            | `conjoint/acbc/estimate.py::attribute_importance`   | `tests/test_acbc_estimate.py::test_attribute_importance_columns_and_normalised` |
| BYO anchor                      | `conjoint/acbc/byo.py::byo_to_anchor`               | `tests/test_acbc_byo_screener.py::test_byo_anchor_uses_provided_answers` |
| Screener pool                   | `conjoint/acbc/screener.py::seed_screener_pool`     | `tests/test_acbc_byo_screener.py::test_seed_screener_pool_distinct_from_anchor` |
| Share of preference             | `conjoint/acbc/simulation.py::share_of_preference`  | `tests/test_acbc_hb_simulation.py::test_share_of_preference_matches_softmax` |
| Removal impact                  | `conjoint/acbc/simulation.py::removal_impact`       | `tests/test_acbc_hb_simulation.py::test_removal_impact_conserves_total_share` |
| Dashboard share transfer       | `dashboard/simulation.py::share_transfer_table`     | `tests/test_dashboard_simulation.py::test_share_transfer_table_uses_acbc_simulation` |

---

## Out of scope

* **`.cho` / `.dat` import** — bring data in by writing the long-format
  CSV directly.
* **D-efficient design optimiser** — the random-balanced + 2-opt
  swap heuristic is good enough for the studied sample sizes
  (n_profiles ≤ 100). A Kuhfeld-style D-efficient optimiser would be a
  drop-in replacement for `generate_profiles`.
* **Multi-language questionnaires** — the spec carries a single
  prompt + label string per attribute.
