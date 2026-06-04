"""Survey landing route — welcome, respondent id capture, mode toggle.

Rendered by the ``survey.py`` ``st.navigation`` router as the default page.
The respondent id is stored in :data:`survey_views.state.RESPONDENT_KEY` so
downstream stages can reuse it. The survey **mode** chooser
(:data:`SURVEY_MODE_KEY`) decides which downstream flow runs — labels are
kept friendly so respondents never see internal terms like ACBC / OLS / MNL.
"""

from __future__ import annotations

import streamlit as st

from survey_views.state import (
    ACBC_BYO_PAGE_KEY,
    QUESTIONNAIRE_PAGE_KEY,
    RESPONDENT_KEY,
    SURVEY_MODE_KEY,
)
from survey_views.theme import apply_base_theme, expect_steps

#: Friendly mode labels (no internal terminology leaks into the UI).
MODE_RATING = "Rate each option (about 5 minutes)"
MODE_ACBC = "Build and compare (about 10 minutes)"
MODE_OPTIONS: tuple[str, ...] = (MODE_ACBC, MODE_RATING)
#: One caption per option, shown under the radio label to explain each method.
_MODE_CAPTIONS: tuple[str, ...] = (
    "Design your ideal phone, then make a few quick comparisons. Recommended.",
    "Rate how appealing each feature option is, one screen at a time.",
)


def render_intro() -> None:
    """Render the welcome / instructions / mode-toggle page."""
    apply_base_theme()
    # ``st.title`` (not a Markdown h1) keeps the page discoverable by the router
    # test, which asserts a title containing "survey".
    st.title("Smartphone preferences survey")
    st.markdown(
        "<p class='lead'>Welcome, and thank you for taking part. This short survey "
        "asks which smartphone features matter most to you — there are no right or "
        "wrong answers, just tell us what you would prefer.</p>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("##### What to expect")
        expect_steps(
            [
                (
                    "Build your ideal",
                    "Pick the option you like best for each feature.",
                ),
                (
                    "Consider a few phones",
                    "Say yes or no to a handful of example phones.",
                ),
                (
                    "Make your final choice",
                    "Choose your favourite in a few side-by-side comparisons.",
                ),
            ]
        )
        st.caption("About 5–10 minutes. Your answers are used only for this study.")

    st.text_input(
        "Your name or an ID (optional)",
        key=RESPONDENT_KEY,
        placeholder="e.g. Alex",
        help="Anything that helps the researcher recognise your responses. "
        "Leave blank if you prefer.",
    )

    st.radio(
        "How would you like to take the survey?",
        options=MODE_OPTIONS,
        captions=_MODE_CAPTIONS,
        index=0,
        key=SURVEY_MODE_KEY,
        horizontal=False,
    )

    mode = st.session_state.get(SURVEY_MODE_KEY, MODE_ACBC)
    target_key = QUESTIONNAIRE_PAGE_KEY if mode == MODE_RATING else ACBC_BYO_PAGE_KEY
    page = st.session_state.get(target_key)

    if page is not None and st.button("Start →", type="primary"):
        st.switch_page(page)
    st.caption("Your answers are confidential and used only for this study.")
