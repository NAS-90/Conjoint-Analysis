"""Survey landing route — welcome + respondent id capture.

Rendered by the ``survey.py`` ``st.navigation`` router as the default page. The
respondent id is stored in :data:`survey_views.state.RESPONDENT_KEY` so
downstream stages can reuse it. There is a single linear flow (no mode chooser),
so "Start" simply opens Part A.
"""

from __future__ import annotations

import streamlit as st

from survey_views.navigation import advance_to
from survey_views.state import PART_A_PAGE_KEY, RESPONDENT_KEY
from survey_views.theme import apply_base_theme, expect_steps


def render_intro() -> None:
    """Render the welcome / instructions / respondent-id page."""
    apply_base_theme()
    # ``st.title`` (not a Markdown h1) keeps the page discoverable by the router
    # test, which asserts a title containing "survey".
    st.title("Product preferences survey")
    st.markdown(
        "<p class='lead'>Welcome, and thank you for taking part. This short survey "
        "asks which features matter most to you — there are no right or "
        "wrong answers, just tell us what you would prefer.</p>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("##### What to expect")
        expect_steps(
            [
                (
                    "Tell us about you",
                    "A few quick background questions and a guide to the features.",
                ),
                (
                    "Share your preferences",
                    "Flag any deal-breakers — features you must have or would never accept.",
                ),
                (
                    "Compare a few options",
                    "Pick your favourite in some side-by-side comparisons.",
                ),
                (
                    "A couple of extras",
                    "How likely you'd buy, and what you'd pay a little more for.",
                ),
            ]
        )
        st.caption("About 8–12 minutes. Your answers are used only for this study.")

    st.text_input(
        "Your name or an ID (optional)",
        key=RESPONDENT_KEY,
        placeholder="e.g. Alex",
        help="Anything that helps the researcher recognise your responses. "
        "Leave blank if you prefer.",
    )

    if st.button("Start →", type="primary"):
        advance_to(PART_A_PAGE_KEY)
    st.caption("Your answers are confidential and used only for this study.")
