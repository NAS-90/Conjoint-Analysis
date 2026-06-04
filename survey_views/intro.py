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
    SURVEY_MODE_CHOICE_KEY,
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


def _persist_mode() -> None:
    """Mirror the radio choice into the non-widget :data:`SURVEY_MODE_KEY`.

    The router gates the sidebar on :data:`SURVEY_MODE_KEY`. If the radio wrote
    its choice there directly, ``st.switch_page`` (the "Start" handler) would
    rerun the script on a *different* page where this radio is not rendered —
    Streamlit then garbage-collects the radio's widget state, the router falls
    back to the ACBC default, and the rating page (absent from that flow) can
    never be reached. Copying into a plain key keeps the choice alive across
    that rerun. Registered as the radio's ``on_change`` so the sidebar updates
    with no one-rerun lag.
    """
    st.session_state[SURVEY_MODE_KEY] = st.session_state[SURVEY_MODE_CHOICE_KEY]


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

    # Seed the widget from the persisted mode so returning to Welcome restores
    # the previous choice. Seeding via session_state (instead of ``index=``)
    # also avoids the "default value will be ignored" warning Streamlit emits
    # when a keyed widget is given both a key and a default.
    st.session_state.setdefault(
        SURVEY_MODE_CHOICE_KEY, st.session_state.get(SURVEY_MODE_KEY, MODE_ACBC)
    )
    st.radio(
        "How would you like to take the survey?",
        options=MODE_OPTIONS,
        captions=_MODE_CAPTIONS,
        key=SURVEY_MODE_CHOICE_KEY,
        on_change=_persist_mode,
        horizontal=False,
    )
    # ``on_change`` only fires on interaction; mirror once on first render too so
    # the router has a mode to gate on before the respondent touches the radio.
    _persist_mode()
    mode = st.session_state[SURVEY_MODE_KEY]

    target_key = QUESTIONNAIRE_PAGE_KEY if mode == MODE_RATING else ACBC_BYO_PAGE_KEY
    page = st.session_state.get(target_key)

    if page is not None and st.button("Start →", type="primary"):
        st.switch_page(page)
    st.caption("Your answers are confidential and used only for this study.")
