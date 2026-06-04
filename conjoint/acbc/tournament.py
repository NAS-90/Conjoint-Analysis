"""ACBC Tournament choice-task assembly.

A *task* is one screen of the Tournament stage: ``K`` profiles shown
side-by-side, the respondent picks the most preferred. We assemble tasks
from a profile pool (see :mod:`conjoint.acbc.design`) into groups of
``alts_per_task`` without repeating a profile inside the same task.

Two regimes, chosen automatically by pool size:

* **Partition** — when the pool is large enough to give every task its own
  disjoint slice (``len(pool) >= n_tasks * alts_per_task``) we shuffle then
  partition, so each profile is used at most once across the whole stage
  (the classic design-pool path used by the estimators / HB simulation).
* **Reuse** — when the pool is smaller (the live ACBC path: only the
  Screener survivors, often a dozen or fewer) we sample ``alts_per_task``
  *distinct* profiles per task and let a profile reappear **across** tasks.
  Tasks are kept distinct as unordered sets so we never show the same
  comparison twice. This is what unblocks the Screener → Tournament hand-off
  — previously ``build_tasks`` hard-required ``n_tasks * alts_per_task``
  profiles and raised for any realistic survivor pool.

Either way a profile never repeats *inside* one task. ``Task`` is a frozen
dataclass; ``chosen_index`` is a separate, mutable per-response field carried
by :mod:`conjoint.acbc.responses`.
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
    """Build ``n_tasks`` choice tasks from ``pool``.

    Each task contains ``alts_per_task`` *distinct* profiles. The order
    inside a task is randomised but reproducible under a fixed ``seed``.

    The only hard requirement is ``len(pool) >= alts_per_task`` (enough to
    fill a single choice set). When the pool is large enough to partition
    (``len(pool) >= n_tasks * alts_per_task``) profiles are used at most
    once across the whole stage; otherwise profiles are reused **across**
    tasks while every task stays a distinct unordered set of profiles.

    If ``n_tasks`` exceeds the number of distinct ``alts_per_task``-sized
    combinations the pool can form, fewer tasks are returned (callers that
    care should size ``n_tasks`` against the pool — see
    :mod:`survey_views.acbc_tournament`).
    """
    if n_tasks <= 0:
        raise ValueError(f"n_tasks must be positive (got {n_tasks})")
    if alts_per_task < 2:
        raise ValueError(
            f"alts_per_task must be >= 2 to constitute a choice (got {alts_per_task})"
        )
    if len(pool) < alts_per_task:
        raise ValueError(
            f"profile pool too small: need at least {alts_per_task} profiles "
            f"to form one task, got {len(pool)}"
        )

    rng = random.Random(seed)
    if len(pool) >= n_tasks * alts_per_task:
        return _partition_tasks(pool, n_tasks=n_tasks, alts_per_task=alts_per_task, rng=rng)
    return _sample_tasks(pool, n_tasks=n_tasks, alts_per_task=alts_per_task, rng=rng)


def _partition_tasks(
    pool: Sequence[Profile],
    *,
    n_tasks: int,
    alts_per_task: int,
    rng: random.Random,
) -> tuple[Task, ...]:
    """Disjoint partition of a large pool — each profile used at most once."""
    order = list(pool)
    rng.shuffle(order)
    tasks: list[Task] = []
    for index in range(n_tasks):
        start = index * alts_per_task
        alternatives = tuple(order[start : start + alts_per_task])
        tasks.append(Task(task_id=index + 1, alternatives=alternatives))
    return tuple(tasks)


def _sample_tasks(
    pool: Sequence[Profile],
    *,
    n_tasks: int,
    alts_per_task: int,
    rng: random.Random,
) -> tuple[Task, ...]:
    """Sample distinct profile-sets, reusing profiles across (not within) tasks."""
    pool = list(pool)
    indices = range(len(pool))
    seen: set[tuple[int, ...]] = set()
    tasks: list[Task] = []
    # Generous attempt budget so we exhaust the distinct combinations a small
    # pool can form before giving up (rather than spinning forever).
    max_attempts = max(n_tasks * 50, 1000)
    attempts = 0
    while len(tasks) < n_tasks and attempts < max_attempts:
        attempts += 1
        chosen = rng.sample(indices, alts_per_task)
        key = tuple(sorted(chosen))  # unordered identity → no duplicate tasks
        if key in seen:
            continue
        seen.add(key)
        rng.shuffle(chosen)  # randomise display order within the task
        alternatives = tuple(pool[i] for i in chosen)
        tasks.append(Task(task_id=len(tasks) + 1, alternatives=alternatives))
    return tuple(tasks)
