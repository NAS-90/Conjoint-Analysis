"""Part A — user screening & background profiling.

The first section of the linear questionnaire. It mirrors the reference
design's *Introduction Questions*: purchase intent, current device, budget and
usage. These answers are for respondent **profiling / segmentation** only — they
do not feed utility estimation — so they are simply recorded into the responses
CSV (stage ``background``).

One question per screen via :func:`survey_views.navigation.render_sequence`; on
Finish the flow advances to B0 (feature explanation).
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    record_answer,
    render_sequence,
)
from survey_views.state import B0_PAGE_KEY
from survey_views.theme import apply_base_theme, flow_header

#: Stage identifier under which Part A answers are stored.
STAGE = "background"


@dataclass(frozen=True)
class ProfileQuestion:
    """One Part A profiling question."""

    identifier: str
    prompt: str
    options: tuple[str, ...]
    multi: bool = False
    help: str = ""


#: The Part A question bank (smartphone reframing of the reference design).
PROFILE_QUESTIONS: tuple[ProfileQuestion, ...] = (
    ProfileQuestion(
        identifier="purchase_timing",
        prompt="When are you most likely to buy your next smartphone?",
        options=("Within 3 months", "3–12 months", "More than a year", "No plans yet"),
    ),
    ProfileQuestion(
        identifier="current_brand",
        prompt="Which brand is your current phone?",
        options=(
            "Apple",
            "Samsung",
            "Xiaomi",
            "Huawei",
            "Google",
            "Another brand",
            "I don't have one",
        ),
    ),
    ProfileQuestion(
        identifier="budget",
        prompt="Roughly what budget do you have in mind?",
        options=("Under $300", "$300 – $700", "Over $700", "Not sure yet"),
    ),
    ProfileQuestion(
        identifier="usage",
        prompt="What do you mainly use your phone for?",
        options=(
            "Calls & messaging",
            "Social media",
            "Photography",
            "Gaming",
            "Work & productivity",
            "Streaming video",
        ),
        multi=True,
        help="Choose all that apply.",
    ),
    ProfileQuestion(
        identifier="top_factor",
        prompt="What matters most to you when choosing a phone?",
        options=("Price", "Performance", "Camera", "Battery life", "Brand", "Screen"),
    ),
)


def _question_step(question: ProfileQuestion) -> Step:
    """Build a :class:`Step` rendering one profiling question."""

    def render() -> bool:
        if question.help:
            st.caption(question.help)
        prior = get_answer(STAGE, question.identifier)
        if question.multi:
            default = list(prior) if isinstance(prior, (list, tuple)) else []
            chosen = st.multiselect(
                question.prompt,
                options=list(question.options),
                default=default,
                key=f"background__{question.identifier}",
                label_visibility="collapsed",
            )
            record_answer(STAGE, question.identifier, list(chosen))
            return len(chosen) > 0
        options = list(question.options)
        index = options.index(prior) if prior in options else None
        chosen = st.radio(
            question.prompt,
            options=options,
            index=index,
            key=f"background__{question.identifier}",
            label_visibility="collapsed",
        )
        if chosen is None:
            return False
        record_answer(STAGE, question.identifier, str(chosen))
        return True

    return Step(identifier=question.identifier, title=question.prompt, render=render)


def render_background() -> None:
    """Render Part A (one profiling question per screen)."""
    apply_base_theme()
    flow_header(
        1,
        7,
        "A few things about you",
        "This helps us understand who is taking part. There are no right answers.",
    )

    steps = tuple(_question_step(q) for q in PROFILE_QUESTIONS)

    def on_complete() -> None:
        advance_to(B0_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Question")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_background()
