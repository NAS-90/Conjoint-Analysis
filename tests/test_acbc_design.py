"""Tests for :mod:`conjoint.acbc.design` and :mod:`conjoint.acbc.tournament`.

These exercise the ACBC experimental-design primitives:

* generating a balanced profile pool from an attribute->levels spec;
* effects-coding the pool into a numerical design matrix;
* turning the pool into Tournament choice tasks.
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

from conjoint.acbc import design as acbc_design
from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.design import Profile, generate_profiles
from conjoint.acbc.tournament import Task, build_tasks


SPEC = OrderedDict(
    [
        ("engine", ("basic", "premium")),
        ("transmission", ("manual", "auto", "cvt")),
        ("cabin", ("open", "closed")),
    ]
)


@pytest.mark.unit
def test_generate_profiles_is_level_balanced() -> None:
    profiles = generate_profiles(SPEC, n_profiles=24, seed=42)
    assert len(profiles) == 24

    counts = acbc_design.check_level_balance(profiles, SPEC)
    # 24 / K levels per attribute → exactly uniform when 24 % K == 0.
    assert counts["engine"] == OrderedDict(basic=12, premium=12)
    assert counts["transmission"] == OrderedDict(manual=8, auto=8, cvt=8)
    assert counts["cabin"] == OrderedDict(open=12, closed=12)
    assert acbc_design.level_balance_deviation(profiles, SPEC) == 0.0


@pytest.mark.unit
def test_generate_profiles_is_reproducible() -> None:
    a = generate_profiles(SPEC, n_profiles=12, seed=7)
    b = generate_profiles(SPEC, n_profiles=12, seed=7)
    assert a == b


@pytest.mark.unit
def test_generate_profiles_rejects_non_positive_n() -> None:
    with pytest.raises(ValueError):
        generate_profiles(SPEC, n_profiles=0, seed=1)


@pytest.mark.unit
def test_effects_code_shape_and_dropped_level() -> None:
    profiles = generate_profiles(SPEC, n_profiles=12, seed=11)
    matrix, columns, level_map = acbc_design.effects_code(profiles, SPEC)

    # K-1 columns per attribute → 1 + 2 + 1 = 4.
    assert matrix.shape == (12, 4)
    assert columns == [
        "engine__basic",
        "transmission__manual",
        "transmission__auto",
        "cabin__open",
    ]
    assert level_map == OrderedDict(
        engine=["basic", "premium"],
        transmission=["manual", "auto", "cvt"],
        cabin=["open", "closed"],
    )

    # Effects coding: each cell is {-1, 0, +1}.
    assert set(np.unique(matrix)).issubset({-1.0, 0.0, 1.0})

    # The dropped level rows are ``-1`` for every column of that attribute.
    for index, profile in enumerate(profiles):
        if profile.level_for("engine") == "premium":
            assert matrix[index, 0] == -1.0
        if profile.level_for("transmission") == "cvt":
            assert matrix[index, 1] == -1.0
            assert matrix[index, 2] == -1.0
        if profile.level_for("cabin") == "closed":
            assert matrix[index, 3] == -1.0


@pytest.mark.unit
def test_orthogonality_check_returns_finite_number() -> None:
    profiles = generate_profiles(SPEC, n_profiles=48, seed=13)
    matrix, _, _ = acbc_design.effects_code(profiles, SPEC)
    score = acbc_design.check_orthogonality(matrix)
    assert score >= 0
    # A balanced design should not have wildly correlated columns.
    assert score < 0.5


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_build_tasks_partitions_pool() -> None:
    profiles = generate_profiles(SPEC, n_profiles=18, seed=21)
    tasks = build_tasks(profiles, n_tasks=6, alts_per_task=3, seed=21)

    assert len(tasks) == 6
    for task in tasks:
        assert isinstance(task, Task)
        assert len(task.alternatives) == 3
        # No duplicate profile inside a task.
        assert len({id(alt) for alt in task.alternatives}) == 3


@pytest.mark.unit
def test_build_tasks_rejects_too_small_pool() -> None:
    profiles = generate_profiles(SPEC, n_profiles=6, seed=2)
    with pytest.raises(ValueError):
        build_tasks(profiles, n_tasks=5, alts_per_task=3, seed=2)


# ---------------------------------------------------------------------------
# Responses long-format
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_assemble_tournament_responses_emits_one_row_per_alternative() -> None:
    profiles = generate_profiles(SPEC, n_profiles=12, seed=5)
    tasks = build_tasks(profiles, n_tasks=4, alts_per_task=3, seed=5)
    answers = [
        acbc_responses.TournamentResponse(respondent="r1", task=task, chosen_index=0)
        for task in tasks
    ]

    frame = acbc_responses.assemble_tournament_responses(answers, SPEC)
    assert len(frame) == 4 * 3
    assert list(frame.columns) == list(acbc_responses.FIXED_COLUMNS) + [
        "engine=level",
        "transmission=level",
        "cabin=level",
    ]
    assert (frame[acbc_responses.STAGE_COL] == acbc_responses.STAGE_TOURNAMENT).all()
    # Exactly one chosen per task.
    for task in tasks:
        block = frame[frame[acbc_responses.TASK_ID_COL] == task.task_id]
        assert block[acbc_responses.CHOSEN_COL].sum() == 1


@pytest.mark.unit
def test_validate_acbc_responses_flags_double_choice() -> None:
    profile = Profile(levels=(("engine", "basic"), ("transmission", "manual"), ("cabin", "open")))
    task = Task(task_id=1, alternatives=(profile, profile))
    answers = [
        acbc_responses.TournamentResponse(respondent="r1", task=task, chosen_index=0),
    ]
    frame = acbc_responses.assemble_tournament_responses(answers, SPEC)
    # Inject a second chosen=1 row on the same task.
    frame.loc[1, acbc_responses.CHOSEN_COL] = 1
    problems = acbc_responses.validate_acbc_responses(frame, SPEC)
    assert any("chosen alternative" in p for p in problems)
