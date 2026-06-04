"""Tests for :mod:`conjoint.acbc.byo` and :mod:`conjoint.acbc.screener`.

Cover:

* BYO question construction from a spec,
* BYO answers → anchor profile (with defaulting for missing answers),
* Screener pool always differs from the anchor by at least one level,
* ``filter_survivors`` keeps Yes votes and drops No votes,
* ``unacceptable_levels`` flags levels rejected ``min_rejections`` times.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import pytest

from conjoint import questionnaire as q
from conjoint.acbc import byo as acbc_byo
from conjoint.acbc import screener as acbc_screener
from conjoint.acbc.design import Profile
from conjoint.acbc.responses import ScreenerResponse

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_SPEC = REPO_ROOT / "questionnaire_spec.json"

ATTRIBUTE_LEVELS = OrderedDict(
    [
        ("engine", ("basic", "premium")),
        ("transmission", ("manual", "auto", "cvt")),
        ("cabin", ("open", "closed")),
    ]
)


# ---------------------------------------------------------------------------
# BYO
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_byo_questions_one_per_active_attribute() -> None:
    spec = q.read_spec(BUNDLED_SPEC)
    questions = acbc_byo.byo_questions(spec)
    assert {item.attribute for item in questions} == {
        attribute.feature_name for attribute in spec.active_attributes
    }
    for question, attribute in zip(questions, spec.active_attributes):
        assert question.levels == tuple(
            (level.code, level.label) for level in attribute.levels
        )


@pytest.mark.unit
def test_byo_anchor_falls_back_to_first_level_for_missing_answers() -> None:
    spec = q.read_spec(BUNDLED_SPEC)
    anchor = acbc_byo.byo_to_anchor({}, spec)
    expected_first = OrderedDict(
        (attribute.feature_name, attribute.levels[0].code)
        for attribute in spec.active_attributes
    )
    assert anchor.as_dict == expected_first


@pytest.mark.unit
def test_byo_anchor_uses_provided_answers() -> None:
    spec = q.read_spec(BUNDLED_SPEC)
    # Pick the last level for every attribute as the answer.
    answers = {
        attribute.feature_name: attribute.levels[-1].code
        for attribute in spec.active_attributes
    }
    anchor = acbc_byo.byo_to_anchor(answers, spec)
    for attribute, code in anchor.levels:
        assert code == answers[attribute]


@pytest.mark.unit
def test_byo_to_responses_skips_missing_and_uses_task_index() -> None:
    answers = {"engine": "premium", "cabin": "closed"}
    records = acbc_byo.byo_to_responses(
        answers,
        respondent="r1",
        attribute_order=["engine", "transmission", "cabin"],
    )
    # transmission absent ⇒ no record for it.
    assert [record.attribute for record in records] == ["engine", "cabin"]
    # task_id matches enumeration position (1-based) in the **order**.
    assert records[0].task_id == 1
    assert records[1].task_id == 3


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_seed_screener_pool_distinct_from_anchor() -> None:
    anchor = Profile(
        levels=(("engine", "basic"), ("transmission", "manual"), ("cabin", "open"))
    )
    # max_changes=2 across (2, 3, 2)-level space caps the unique perturbations
    # at 9; ask for 8 to give the heuristic headroom while still exercising it.
    profiles = acbc_screener.seed_screener_pool(
        anchor, ATTRIBUTE_LEVELS, n_profiles=8, max_changes=2, seed=7
    )
    assert len(profiles) == 8
    assert len({tuple(p.levels) for p in profiles}) == 8
    for profile in profiles:
        assert profile.levels != anchor.levels
        differences = sum(
            1
            for (a_attr, a_code), (b_attr, b_code) in zip(profile.levels, anchor.levels)
            if a_code != b_code
        )
        assert 1 <= differences <= 2


@pytest.mark.unit
def test_seed_screener_pool_requires_multi_level_attribute() -> None:
    single = OrderedDict([("engine", ("only",))])
    anchor = Profile(levels=(("engine", "only"),))
    with pytest.raises(ValueError):
        acbc_screener.seed_screener_pool(anchor, single, n_profiles=3, seed=1)


@pytest.mark.unit
def test_filter_survivors_keeps_only_yes_votes() -> None:
    profiles = [
        Profile(levels=(("engine", "basic"),)),
        Profile(levels=(("engine", "premium"),)),
    ]
    responses = [
        ScreenerResponse(respondent="r1", task_id=1, profile=profiles[0], accepted=True),
        ScreenerResponse(respondent="r1", task_id=2, profile=profiles[1], accepted=False),
    ]
    survivors = acbc_screener.filter_survivors(responses, threshold=1)
    assert survivors == (profiles[0],)


@pytest.mark.unit
def test_unacceptable_levels_flags_consistent_rejections() -> None:
    """A level rejected in ``min_rejections`` profiles is flagged."""
    responses = [
        ScreenerResponse(
            respondent="r1",
            task_id=1,
            profile=Profile(levels=(("engine", "basic"), ("cabin", "open"))),
            accepted=False,
        ),
        ScreenerResponse(
            respondent="r1",
            task_id=2,
            profile=Profile(levels=(("engine", "basic"), ("cabin", "closed"))),
            accepted=False,
        ),
        ScreenerResponse(
            respondent="r1",
            task_id=3,
            profile=Profile(levels=(("engine", "premium"), ("cabin", "open"))),
            accepted=True,
        ),
    ]
    flagged = acbc_screener.unacceptable_levels(responses, min_rejections=2)
    # 'engine=basic' appears in two rejected profiles.
    assert flagged == {"engine": {"basic"}}
