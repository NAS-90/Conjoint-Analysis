"""ACBC (Adaptive Choice-Based Conjoint) algorithm + UI components.

Public modules:

* :mod:`conjoint.acbc.design` — profile generation, level balance,
  minimal-overlap heuristic, effects-coded design matrix.
* :mod:`conjoint.acbc.tournament` — choice-task assembly + ``Task``
  dataclass.
* :mod:`conjoint.acbc.responses` — long-format ``acbc_responses.csv``
  schema + assemble / validate helpers.
* :mod:`conjoint.acbc.estimate` — MNL log-likelihood, scipy-backed fit,
  Root-Likelihood (RLH) diagnostic, attribute-importance writer
  (compatible with :mod:`conjoint.io`'s ``importance.csv``).
* :mod:`conjoint.acbc.byo` (Phase 3) — Build-Your-Own anchor.
* :mod:`conjoint.acbc.screener` (Phase 3) — Screener Yes/No filtering.
* :mod:`conjoint.acbc.simulation` (Phase 4) — share-of-preference,
  randomized first choice, removal impact.
"""

from __future__ import annotations
