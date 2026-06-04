"""Tests for :mod:`conjoint.acbc.quality` — §8 data-quality screening.

Build controlled long-format Tournament frames with known pathologies
(straightlining, dominated picks, missing tasks, fast completers) and assert
each check fires only where it should.
"""

from __future__ import annotations

from collections import OrderedDict

import pandas as pd
import pytest

from conjoint.acbc import quality
from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.design import Profile
from conjoint.acbc.tournament import Task

ATTRS = OrderedDict([("a", ("a1", "a2")), ("b", ("b1", "b2"))])

# Per-level utilities: a1/b1 are strictly better than a2/b2.
LEVEL_UTILITIES = {
    "a": {"a1": 1.0, "a2": 0.0},
    "b": {"b1": 1.0, "b2": 0.0},
}


def _profile(a: str, b: str) -> Profile:
    return Profile(levels=(("a", a), ("b", b)))


def _assemble(answers: list[acbc_responses.TournamentResponse]) -> pd.DataFrame:
    return acbc_responses.assemble_tournament_responses(answers, ATTRS)


def _alts(*pairs: tuple[str, str]) -> tuple[Profile, ...]:
    return tuple(_profile(a, b) for a, b in pairs)


# ---------------------------------------------------------------------------
# Straightlining / non-differentiation
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_straightlining_flags_constant_position() -> None:
    answers: list[acbc_responses.TournamentResponse] = []
    for task_id in range(1, 6):  # 5 tasks
        task = Task(task_id=task_id, alternatives=_alts(("a1", "b1"), ("a2", "b2"), ("a1", "b2")))
        # "straight" always picks position 0; "varied" rotates.
        answers.append(acbc_responses.TournamentResponse("straight", task, chosen_index=0))
        answers.append(
            acbc_responses.TournamentResponse("varied", task, chosen_index=task_id % 3)
        )
    flags = quality.screen_quality(_assemble(answers))

    by_resp = flags.set_index(acbc_responses.RESPONDENT_COL)
    assert bool(by_resp.loc["straight", quality.STRAIGHTLINING_COL]) is True
    assert bool(by_resp.loc["varied", quality.STRAIGHTLINING_COL]) is False


@pytest.mark.unit
def test_straightlining_needs_min_tasks() -> None:
    # Only 2 tasks → below default min_tournament_tasks (3); not flagged.
    answers = [
        acbc_responses.TournamentResponse(
            "short", Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=0
        )
        for t in (1, 2)
    ]
    flags = quality.screen_quality(_assemble(answers))
    assert bool(flags.iloc[0][quality.STRAIGHTLINING_COL]) is False


# ---------------------------------------------------------------------------
# Inconsistent / illogical (dominated) choices
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_inconsistent_choice_detects_dominated_pick() -> None:
    # alt0 = (a1,b1) dominates alt1 = (a2,b2). Picking alt1 is illogical.
    answers = [
        acbc_responses.TournamentResponse(
            "illogical",
            Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))),
            chosen_index=1,
        )
        for t in range(1, 5)
    ]
    # A rational respondent on the same tasks always takes the dominant alt.
    answers += [
        acbc_responses.TournamentResponse(
            "rational",
            Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))),
            chosen_index=0,
        )
        for t in range(1, 5)
    ]
    flags = quality.screen_quality(_assemble(answers), level_utilities=LEVEL_UTILITIES)
    by_resp = flags.set_index(acbc_responses.RESPONDENT_COL)

    assert bool(by_resp.loc["illogical", quality.INCONSISTENT_COL]) is True
    assert by_resp.loc["illogical", quality.INCONSISTENT_FRACTION_COL] == pytest.approx(1.0)
    assert bool(by_resp.loc["rational", quality.INCONSISTENT_COL]) is False
    assert by_resp.loc["rational", quality.INCONSISTENT_FRACTION_COL] == pytest.approx(0.0)


@pytest.mark.unit
def test_inconsistent_skipped_without_utilities() -> None:
    answers = [
        acbc_responses.TournamentResponse(
            "x", Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=1
        )
        for t in range(1, 4)
    ]
    flags = quality.screen_quality(_assemble(answers))  # no level_utilities
    assert bool(flags.iloc[0][quality.INCONSISTENT_COL]) is False


# ---------------------------------------------------------------------------
# Incomplete interviews
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_incomplete_flags_short_interview() -> None:
    answers: list[acbc_responses.TournamentResponse] = []
    # "full" respondents complete 4 tasks; "short" completes 2.
    for resp in ("full_a", "full_b", "full_c"):
        for t in range(1, 5):
            answers.append(
                acbc_responses.TournamentResponse(
                    resp, Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=0
                )
            )
    for t in range(1, 3):
        answers.append(
            acbc_responses.TournamentResponse(
                "short", Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=0
            )
        )
    flags = quality.screen_quality(_assemble(answers))
    by_resp = flags.set_index(acbc_responses.RESPONDENT_COL)
    assert bool(by_resp.loc["short", quality.INCOMPLETE_COL]) is True
    assert bool(by_resp.loc["full_a", quality.INCOMPLETE_COL]) is False


@pytest.mark.unit
def test_incomplete_flags_unanswered_task() -> None:
    answers = [
        acbc_responses.TournamentResponse(
            "r", Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=0
        )
        for t in range(1, 4)
    ]
    frame = _assemble(answers)
    # Wipe the choice on task 2 → an unanswered task.
    frame.loc[frame[acbc_responses.TASK_ID_COL] == 2, acbc_responses.CHOSEN_COL] = 0
    flags = quality.screen_quality(frame, expected_tasks=3)
    assert bool(flags.iloc[0][quality.INCOMPLETE_COL]) is True


# ---------------------------------------------------------------------------
# Speeding (optional)
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_speeding_flags_fast_respondent_when_duration_present() -> None:
    answers: list[acbc_responses.TournamentResponse] = []
    for resp in ("slow1", "slow2", "slow3", "fast"):
        for t in range(1, 4):
            answers.append(
                acbc_responses.TournamentResponse(
                    resp, Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=0
                )
            )
    frame = _assemble(answers)
    durations = {"slow1": 30.0, "slow2": 40.0, "slow3": 50.0, "fast": 1.0}
    frame = frame.assign(
        duration=frame[acbc_responses.RESPONDENT_COL].map(durations)
    )
    flags = quality.screen_quality(frame, duration_col="duration")
    by_resp = flags.set_index(acbc_responses.RESPONDENT_COL)
    assert bool(by_resp.loc["fast", quality.SPEEDING_COL]) is True
    assert bool(by_resp.loc["slow3", quality.SPEEDING_COL]) is False

    summary = quality.quality_summary(flags)
    assert summary["speeding_checked"] is True
    assert summary[quality.SPEEDING_COL] == 1


@pytest.mark.unit
def test_speeding_skipped_without_duration_column() -> None:
    answers = [
        acbc_responses.TournamentResponse(
            "r", Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=0
        )
        for t in range(1, 4)
    ]
    flags = quality.screen_quality(_assemble(answers))
    assert flags.iloc[0][quality.SPEEDING_COL] is pd.NA or pd.isna(flags.iloc[0][quality.SPEEDING_COL])

    summary = quality.quality_summary(flags)
    assert summary["speeding_checked"] is False
    assert summary[quality.SPEEDING_COL] == 0


# ---------------------------------------------------------------------------
# Orchestration / summary / edges
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_screen_quality_returns_contract_columns_and_does_not_mutate() -> None:
    answers = [
        acbc_responses.TournamentResponse(
            "r", Task(task_id=t, alternatives=_alts(("a1", "b1"), ("a2", "b2"))), chosen_index=0
        )
        for t in range(1, 4)
    ]
    frame = _assemble(answers)
    before = frame.copy(deep=True)
    flags = quality.screen_quality(frame)
    assert list(flags.columns) == list(quality.FLAG_COLUMNS)
    pd.testing.assert_frame_equal(frame, before)  # input untouched


@pytest.mark.unit
def test_screen_quality_empty_without_tournament() -> None:
    empty = pd.DataFrame(columns=[acbc_responses.STAGE_COL])
    flags = quality.screen_quality(empty)
    assert list(flags.columns) == list(quality.FLAG_COLUMNS)
    assert flags.empty
    summary = quality.quality_summary(flags)
    assert summary["n_respondents"] == 0


@pytest.mark.unit
def test_thresholds_validate() -> None:
    with pytest.raises(ValueError):
        quality.QualityThresholds(min_tournament_tasks=0)
    with pytest.raises(ValueError):
        quality.QualityThresholds(speeding_quantile=1.0)
    with pytest.raises(ValueError):
        quality.QualityThresholds(max_inconsistent_fraction=1.5)
