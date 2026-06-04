"""Synthetic ACBC responses for demos, dashboards and tests.

Builds a long-format ``acbc_responses.csv`` from a *known* utility vector, then
deliberately injects the four §8 data-quality pathologies so the screen and
diagnostics have something real to surface:

* **good** — attentive respondents whose choices follow the true utilities
  (Gumbel-noised argmax), the healthy majority.
* **straightliner** — always picks the same position (``alternative_index == 0``).
* **illogical** — always picks the *worst* alternative by true utility (so it
  routinely selects strictly dominated concepts).
* **incomplete** — answers only the first half of the tournament.
* **speeder** — attentive but races through (tiny per-task duration).

A per-row ``duration`` column is emitted so the optional speeding check has
input. The default spec keeps ``price`` ordered low→high so the monotonicity
diagnostic is meaningful, and the true β makes cheaper strictly better.
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pandas as pd

from conjoint.acbc import responses as R
from conjoint.acbc.design import effects_code, generate_profiles
from conjoint.acbc.tournament import build_tasks

#: Demo attribute → levels. ``price`` is ordered budget→premium.
DEMO_SPEC: "OrderedDict[str, tuple[str, ...]]" = OrderedDict(
    [
        ("price", ("budget", "mid", "premium")),
        ("ram", ("4gb", "8gb", "12gb")),
        ("camera", ("12mp", "50mp")),
        ("battery", ("small", "large")),
    ]
)

#: Price levels in increasing-price order (for the monotonicity check).
PRICE_ATTRIBUTE = "price"
PRICE_ORDER: tuple[str, ...] = ("budget", "mid", "premium")

#: Effects-coded true β, surviving levels per attribute in :data:`DEMO_SPEC`
#: order: price(budget, mid), ram(4gb, 8gb), camera(12mp), battery(small).
#: ⇒ price utilities (0.9, 0.0, -0.9) decrease with price (logical); ram peaks
#: at 8gb; camera/battery favour the richer level. Price range 1.8 is the
#: largest but ~0.45 relative importance, so no attribute over-dominates.
DEMO_BETA = np.array([0.9, 0.0, -0.3, 0.5, -0.4, -0.3])

# Per-task answering time (seconds) by respondent type — speeders are an order
# of magnitude faster so they sit unambiguously in the bottom duration quantile.
_DURATION_BASE = {
    "good": 18.0,
    "straightliner": 12.0,
    "illogical": 14.0,
    "incomplete": 18.0,
    "speeder": 1.0,
}


def _cohort(
    n_good: int, n_straightliner: int, n_illogical: int, n_incomplete: int, n_speeder: int
) -> list[tuple[str, str]]:
    """Ordered ``(respondent_id, kind)`` list with stable zero-padded ids."""
    plan = [
        ("good", n_good),
        ("straightliner", n_straightliner),
        ("illogical", n_illogical),
        ("incomplete", n_incomplete),
        ("speeder", n_speeder),
    ]
    cohort: list[tuple[str, str]] = []
    index = 0
    for kind, count in plan:
        for _ in range(count):
            index += 1
            cohort.append((f"r{index:03d}", kind))
    return cohort


def _chosen_index(kind: str, utilities: np.ndarray, rng: np.random.Generator) -> int:
    """Pick an alternative according to the respondent ``kind``."""
    if kind == "straightliner":
        return 0
    if kind == "illogical":
        return int(np.argmin(utilities))
    # good / incomplete / speeder are attentive: Gumbel-noised argmax (MNL draw).
    return int(np.argmax(utilities + rng.gumbel(size=utilities.shape)))


def generate_demo_responses(
    *,
    n_good: int = 90,
    n_straightliner: int = 6,
    n_illogical: int = 6,
    n_incomplete: int = 6,
    n_speeder: int = 6,
    n_tasks: int = 12,
    alts_per_task: int = 3,
    pool_size: int = 96,
    seed: int = 2026,
    spec: "OrderedDict[str, tuple[str, ...]]" = DEMO_SPEC,
    beta: np.ndarray = DEMO_BETA,
) -> pd.DataFrame:
    """Generate a long-format demo frame with injected §8 pathologies.

    Returns the standard :mod:`conjoint.acbc.responses` schema plus a
    ``duration`` column (per-row task time in seconds).
    """
    rng = np.random.default_rng(seed)
    profiles = generate_profiles(spec, n_profiles=pool_size, seed=seed)
    cohort = _cohort(n_good, n_straightliner, n_illogical, n_incomplete, n_speeder)
    if not cohort:
        raise ValueError("at least one respondent is required")

    type_by_respondent: dict[str, str] = {}
    answers: list[R.TournamentResponse] = []
    for respondent, kind in cohort:
        type_by_respondent[respondent] = kind
        tasks = build_tasks(
            profiles,
            n_tasks=n_tasks,
            alts_per_task=alts_per_task,
            seed=int(rng.integers(0, 2**31 - 1)),
        )
        n_answered = n_tasks if kind != "incomplete" else max(1, n_tasks // 2)
        for position, task in enumerate(tasks):
            if position >= n_answered:
                break  # incomplete interview — drops the tail of the tournament
            utilities = effects_code(task.alternatives, spec)[0] @ beta
            answers.append(
                R.TournamentResponse(
                    respondent=respondent,
                    task=task,
                    chosen_index=_chosen_index(kind, utilities, rng),
                )
            )

    frame = R.assemble_tournament_responses(answers, spec)

    duration_rng = np.random.default_rng(seed + 1)
    durations: list[float] = []
    for respondent in frame[R.RESPONDENT_COL]:
        base = _DURATION_BASE[type_by_respondent[respondent]]
        seconds = max(0.2, float(duration_rng.normal(base, base * 0.15)))
        durations.append(round(seconds, 2))
    return frame.assign(duration=durations)
