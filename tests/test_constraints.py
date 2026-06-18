"""Unit tests for :mod:`conjoint.acbc.constraints` (B1 → B2 → B4 bridge)."""

from __future__ import annotations

import pytest

from conjoint.acbc.constraints import (
    VERDICT_MUST_HAVE,
    VERDICT_UNACCEPTABLE,
    anchor_from_ratings,
    filter_by_constraints,
    split_constraints,
)
from conjoint.acbc.design import Profile
from conjoint.questionnaire import AttributeQuestion, Level, QuestionnaireSpec, Scale


def _spec() -> QuestionnaireSpec:
    return QuestionnaireSpec(
        attributes=(
            AttributeQuestion(
                "os", "", "B1_rating", "rating", "",
                (Level("android", "Android"), Level("ios", "iOS")),
                "active", Scale(1, 5),
            ),
            AttributeQuestion(
                "storage", "", "B1_rating", "rating", "",
                (Level("64gb", "64"), Level("128gb", "128"), Level("256gb", "256")),
                "active", Scale(1, 5),
            ),
        )
    )


# ---------------------------------------------------------------------------
# anchor_from_ratings
# ---------------------------------------------------------------------------
def test_anchor_picks_highest_rated_level() -> None:
    ratings = {"os": {"android": 5, "ios": 1}, "storage": {"64gb": 1, "128gb": 5, "256gb": 3}}
    anchor = anchor_from_ratings(ratings, _spec())
    assert anchor.as_dict == {"os": "android", "storage": "128gb"}


def test_anchor_respects_must_have_over_ratings() -> None:
    ratings = {"os": {"android": 5, "ios": 1}}
    anchor = anchor_from_ratings(ratings, _spec(), must_have={"os": "ios"})
    assert anchor.as_dict["os"] == "ios"


def test_anchor_avoids_unacceptable_level() -> None:
    ratings = {"os": {"android": 5, "ios": 1}}
    anchor = anchor_from_ratings(ratings, _spec(), unacceptable={"os": {"android"}})
    assert anchor.as_dict["os"] == "ios"


def test_anchor_breaks_ties_by_spec_order() -> None:
    ratings = {"storage": {"64gb": 3, "128gb": 3, "256gb": 1}}
    anchor = anchor_from_ratings(ratings, _spec())
    assert anchor.as_dict["storage"] == "64gb"  # first of the tied maxima


def test_anchor_defaults_to_first_level_without_ratings() -> None:
    anchor = anchor_from_ratings({}, _spec())
    assert anchor.as_dict == {"os": "android", "storage": "64gb"}


def test_anchor_falls_back_when_all_levels_unacceptable() -> None:
    ratings = {"os": {"android": 5, "ios": 1}}
    anchor = anchor_from_ratings(
        ratings, _spec(), unacceptable={"os": {"android", "ios"}}
    )
    # Contradiction: ignore the exclusion rather than crash; still a valid level.
    assert anchor.as_dict["os"] in {"android", "ios"}


# ---------------------------------------------------------------------------
# filter_by_constraints
# ---------------------------------------------------------------------------
def _profiles() -> tuple[Profile, ...]:
    return (
        Profile((("os", "android"), ("storage", "64gb"))),
        Profile((("os", "ios"), ("storage", "128gb"))),
        Profile((("os", "ios"), ("storage", "64gb"))),
    )


def test_filter_drops_unacceptable_levels() -> None:
    kept = filter_by_constraints(_profiles(), unacceptable={"storage": {"64gb"}})
    assert all(p.as_dict["storage"] != "64gb" for p in kept)
    assert len(kept) == 1


def test_filter_forces_must_have_level() -> None:
    kept = filter_by_constraints(_profiles(), must_have={"os": "ios"})
    assert all(p.as_dict["os"] == "ios" for p in kept)
    assert len(kept) == 2


def test_filter_without_constraints_keeps_everything() -> None:
    profiles = _profiles()
    assert filter_by_constraints(profiles) == profiles


# ---------------------------------------------------------------------------
# split_constraints
# ---------------------------------------------------------------------------
def test_split_constraints_folds_verdicts() -> None:
    verdicts = {
        "os": {"ios": VERDICT_MUST_HAVE},
        "storage": {"64gb": VERDICT_UNACCEPTABLE, "128gb": VERDICT_UNACCEPTABLE},
    }
    must_have, unacceptable = split_constraints(verdicts)
    assert must_have == {"os": "ios"}
    assert unacceptable == {"storage": {"64gb", "128gb"}}


def test_split_constraints_keeps_first_must_have_per_attribute() -> None:
    verdicts = {"os": {"ios": VERDICT_MUST_HAVE, "android": VERDICT_MUST_HAVE}}
    must_have, _ = split_constraints(verdicts)
    assert must_have == {"os": "ios"}


@pytest.mark.parametrize("verdicts", [{}, {"os": {}}])
def test_split_constraints_empty(verdicts) -> None:
    assert split_constraints(verdicts) == ({}, {})
