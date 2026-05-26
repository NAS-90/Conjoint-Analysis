"""Survey landing route — instructions, mode toggle, respondent id capture.

Rendered by the ``survey.py`` ``st.navigation`` router as the default page.
The respondent id is stored in :data:`survey_views.state.RESPONDENT_KEY`
so downstream stages can reuse it. The survey **mode** chooser
(:data:`SURVEY_MODE_KEY`) decides whether the respondent runs:

* the legacy **Part B-1 ratings** flow (OLS path, current dashboard), or
* the **ACBC** flow (Tournament now; BYO + Screener as Phase 3 adds
  them) which produces the long-format ``acbc_responses.csv`` consumed
  by :mod:`conjoint.acbc.estimate`.
"""

from __future__ import annotations

import streamlit as st

from survey_views.state import (
    ACBC_TOURNAMENT_PAGE_KEY,
    QUESTIONNAIRE_PAGE_KEY,
    RESPONDENT_KEY,
    SURVEY_MODE_KEY,
)

MODE_RATING = "Part B-1 ratings (OLS)"
MODE_ACBC = "ACBC Tournament (MNL)"
MODE_OPTIONS: tuple[str, ...] = (MODE_RATING, MODE_ACBC)


def render_intro() -> None:
    """Render the welcome / instructions / mode-toggle page."""
    st.title("Conjoint desirability survey")
    st.markdown(
        """
        Welcome 👋 This survey lets you express preferences over a set of
        product configurations.

        **Two modes are available:**

        * **Part B-1 ratings (OLS)** — rate the desirability of each level
          on a 1..5 scale, one attribute per page. Feeds the existing OLS
          pipeline (`python -m conjoint.estimate`).
        * **ACBC Tournament (MNL)** — pick your favourite from a small
          set of profiles, one task per page. Feeds the multinomial-logit
          pipeline (`python -m conjoint.acbc.estimate`).

        Either path produces the importance.csv that powers the
        customer-weighted distance dashboard.
        """
    )

    st.text_input(
        "Your respondent id",
        key=RESPONDENT_KEY,
        placeholder="e.g. 1",
        help="Any label that identifies this response (defaults to 1 if left blank).",
    )

    st.radio(
        "Survey mode",
        options=MODE_OPTIONS,
        index=0,
        key=SURVEY_MODE_KEY,
        horizontal=True,
    )

    mode = st.session_state.get(SURVEY_MODE_KEY, MODE_RATING)
    target_key = (
        QUESTIONNAIRE_PAGE_KEY if mode == MODE_RATING else ACBC_TOURNAMENT_PAGE_KEY
    )
    page = st.session_state.get(target_key)

    label = "Start ratings →" if mode == MODE_RATING else "Start Tournament →"
    if page is not None and st.button(label, type="primary"):
        st.switch_page(page)
    st.caption("You can also use the **sidebar** to jump between routes.")
