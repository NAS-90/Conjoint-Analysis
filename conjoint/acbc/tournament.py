"""ACBC Tournament choice-task assembly.

A *task* is one screen of the Tournament stage: ``K`` profiles shown
side-by-side, the respondent picks the most preferred. We assemble tasks
from a profile pool (see :mod:`conjoint.acbc.design`) into groups of
``alts_per_task`` without repeating a profile inside the same task.

Implementation notes:

* Profiles are shuffled then partitioned, so each profile is used at
  most once per task and approximately ``n_tasks * alts_per_task /
  len(pool)`` times overall.
* ``Task`` is a frozen dataclass; ``chosen_index`` is a separate, mutable
  per-response field carried by :mod:`conjoint.acbc.responses`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from conjoint.acbc.design import Profile


@dataclass(frozen=True)
class Task:
    """One Tournament choice task: alternative profiles + an id."""

    task_id: int
    alternatives: tuple[Profile, ...]


def build_tasks(
    pool: Sequence[Profile],
    *,
    n_tasks: int,
    alts_per_task: int = 3,
    seed: int | None = None,
) -> tuple[Task, ...]:
    """Partition ``pool`` into ``n_tasks`` choice tasks.

    Each task contains ``alts_per_task`` distinct profiles drawn from
    ``pool``. Profiles are shuffled before partitioning, so the order
    inside a task is randomised but reproducible under a fixed ``seed``.
    """
    if n_tasks <= 0:
        raise ValueError(f"n_tasks must be positive (got {n_tasks})")
    if alts_per_task < 2:
        raise ValueError(
            f"alts_per_task must be >= 2 to constitute a choice (got {alts_per_task})"
        )
    needed = n_tasks * alts_per_task
    if needed > len(pool):
        raise ValueError(
            f"profile pool too small: need {needed} profiles, got {len(pool)}"
        )

    rng = random.Random(seed)
    order = list(pool)
    rng.shuffle(order)

    tasks: list[Task] = []
    for index in range(n_tasks):
        start = index * alts_per_task
        end = start + alts_per_task
        alternatives = tuple(order[start:end])
        tasks.append(Task(task_id=index + 1, alternatives=alternatives))
    return tuple(tasks)
