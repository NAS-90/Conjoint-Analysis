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

import streamlit as st

from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    record_answer,
    render_sequence,
)
from survey_views.section_source import (
    DEFAULT_PROFILE_QUESTIONS,
    ProfileQuestion,
    load_background_questions,
)
from survey_views.state import B0_PAGE_KEY
from survey_views.theme import apply_base_theme, flow_header

#: Stage identifier under which Part A answers are stored.
STAGE = "background"

#: Built-in default question bank (used when ``survey_questions.json`` is absent).
#: Re-exported here for back-compat; the live questions come from
#: :func:`survey_views.section_source.load_background_questions`.
PROFILE_QUESTIONS: tuple[ProfileQuestion, ...] = DEFAULT_PROFILE_QUESTIONS


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
        6,
        "A few things about you",
        "This helps us understand who is taking part. There are no right answers.",
    )

    steps = tuple(_question_step(q) for q in load_background_questions())

    def on_complete() -> None:
        advance_to(B0_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Question")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_background()
