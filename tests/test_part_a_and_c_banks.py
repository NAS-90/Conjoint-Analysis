"""Sanity checks for the Part A / Part C hardcoded question banks."""

from __future__ import annotations

from survey_views.part_a_background import PROFILE_QUESTIONS
from survey_views.part_c_wtp import AMOUNT_BANDS, WTP_FEATURES


def test_profile_questions_are_well_formed() -> None:
    ids = [q.identifier for q in PROFILE_QUESTIONS]
    assert len(ids) == len(set(ids)), "Part A question ids must be unique"
    for question in PROFILE_QUESTIONS:
        assert question.prompt.strip()
        assert len(question.options) >= 2
        assert len(question.options) == len(set(question.options))


def test_wtp_features_are_well_formed() -> None:
    ids = [f.identifier for f in WTP_FEATURES]
    assert len(ids) == len(set(ids)), "Part C feature ids must be unique"
    assert all(f.label.strip() for f in WTP_FEATURES)


def test_amount_bands_are_well_formed() -> None:
    codes = [code for code, _ in AMOUNT_BANDS]
    assert len(codes) >= 2
    assert len(codes) == len(set(codes)), "amount band codes must be unique"
    assert all(label.strip() for _, label in AMOUNT_BANDS)
