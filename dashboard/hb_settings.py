"""Shared Hierarchical-Bayes sampler settings for the dashboard pages.

Both analysis cores (:mod:`dashboard.results_analysis` and
:mod:`dashboard.quality_diagnostics`) fit the same model on the same data, so
they must use the same sampler budget: otherwise the two pages report different
Rhat values and different per-respondent βs for one dataset. Keeping the numbers
here is what stops them drifting apart again.

Why these values: with a full attribute set (roughly 14 effects-coded features)
the sampler needs ~20000 iterations to bring Gelman-Rubin Rhat under 1.1. Fewer
iterations do not merely lose precision, they leave the chains visibly
unconverged, and the quality page turns per-respondent β into keep/drop calls.
That makes this the slow path, single-digit minutes on a full sample, so every
caller is expected to cache the result.
"""

from __future__ import annotations

#: MCMC iterations per chain. Half is burned in (see ``burn_in=HB_ITERATIONS // 2``).
HB_ITERATIONS = 20000

#: Keep every n-th post-burn-in draw. Thinning also caps peak memory: the
#: sampler holds one (n_respondents, n_features) snapshot per retained draw.
HB_THINNING = 10

#: Fixed seed so a given dataset always produces the same published read-out.
HB_SEED = 0

#: Preview budget for smoke tests and interactive spot-checks. Fast, and NOT
#: converged: never use it for a published figure or a keep/drop decision.
HB_PREVIEW_ITERATIONS = 400
