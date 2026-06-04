"""Survey landing route — instructions + respondent id capture.

Rendered by the ``survey.py`` ``st.navigation`` router as the default page. The
respondent id is stored in :data:`survey_views.state.RESPONDENT_KEY` so the
ratings page can reuse it when assembling ``responses.csv``.
"""

from __future__ import annotations

import streamlit as st

from survey_views.state import QUESTIONNAIRE_PAGE_KEY, RESPONDENT_KEY


def render_intro() -> None:
    """Render the welcome / instructions page."""
    st.title("Conjoint desirability survey")
    st.markdown("""
        Welcome 👋 This short survey is **Part B-1** of a conjoint study on
        tractor configurations.

        The ratings page can show the full questionnaire, a guided profile, or a
        custom attribute subset. For each visible configuration **attribute**
        you'll see its possible **levels**. Rate **how desirable each level is to
        you** from **1 (least desirable)** to **5 (most desirable)**. There are
        no right answers — we're after your personal preference.

        Your ratings are assembled into a `responses.csv` that drives the
        part-worth / relative-importance estimation
        (`python -m conjoint.estimate`).
        """)

    st.text_input(
        "Your respondent id",
        key=RESPONDENT_KEY,
        placeholder="e.g. 1",
        help="Any label that identifies this response (defaults to 1 if left blank).",
    )

    page = st.session_state.get(QUESTIONNAIRE_PAGE_KEY)
    if page is not None and st.button("Start the questionnaire →", type="primary"):
        st.switch_page(page)
    st.caption("You can also use the **sidebar** to jump to *Part B-1 ratings*.")
