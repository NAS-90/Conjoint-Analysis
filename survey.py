"""Standalone conjoint survey app — its own ``st.navigation`` router.

Decoupled from the analysis dashboard (``app.py``): a respondent opens
this app on its own URL, picks a mode on the intro page and works
through the chosen flow.

Launch with::

    streamlit run survey.py        # or: ./run.sh survey

Routes (rendered in the sidebar nav, grouped under "Survey"):

* **Welcome** — instructions, respondent id, survey-mode toggle
  (:mod:`survey_views.intro`).
* **Part B-1 ratings** — single-page-per-attribute desirability flow
  (:mod:`survey_views.ratings`); on Finish it builds + validates a
  downloadable ``responses.csv`` for :mod:`conjoint.estimate`.
* **ACBC BYO** — single-page-per-attribute "pick favourite" flow
  (:mod:`survey_views.acbc_byo`); writes the anchor profile to session
  state.
* **ACBC Screener** — single-page-per-profile Yes/No filtering of the
  BYO-anchored pool (:mod:`survey_views.acbc_screener`); writes the
  survivors to session state.
* **ACBC Tournament** — single-page-per-choice-task flow
  (:mod:`survey_views.acbc_tournament`); uses Screener survivors when
  available, otherwise a balanced random pool.
* **ACBC Summary** — merged BYO + Screener + Tournament CSV
  (:mod:`survey_views.acbc_summary`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # allow ``streamlit run survey.py`` from anywhere
    sys.path.insert(0, str(ROOT))

from survey_views.acbc_byo import render_byo  # noqa: E402
from survey_views.acbc_screener import render_screener  # noqa: E402
from survey_views.acbc_summary import render_summary  # noqa: E402
from survey_views.acbc_tournament import render_tournament  # noqa: E402
from survey_views.intro import render_intro  # noqa: E402
from survey_views.ratings import render_questionnaire  # noqa: E402
from survey_views.state import (  # noqa: E402
    ACBC_BYO_PAGE_KEY,
    ACBC_SCREENER_PAGE_KEY,
    ACBC_SUMMARY_PAGE_KEY,
    ACBC_TOURNAMENT_PAGE_KEY,
    QUESTIONNAIRE_PAGE_KEY,
)


def main() -> None:
    """Configure the page and run the survey navigation router."""
    st.set_page_config(page_title="Conjoint survey", page_icon="📝", layout="centered")

    intro_page = st.Page(
        render_intro, title="Welcome", icon="👋", url_path="welcome", default=True
    )
    questionnaire_page = st.Page(
        render_questionnaire, title="Part B-1 ratings", icon="📝", url_path="ratings"
    )
    byo_page = st.Page(
        render_byo, title="ACBC BYO", icon="🧩", url_path="acbc-byo"
    )
    screener_page = st.Page(
        render_screener, title="ACBC Screener", icon="🔎", url_path="acbc-screener"
    )
    tournament_page = st.Page(
        render_tournament,
        title="ACBC Tournament",
        icon="🏆",
        url_path="acbc-tournament",
    )
    summary_page = st.Page(
        render_summary, title="ACBC Summary", icon="📦", url_path="acbc-summary"
    )

    # Stash page handles so cross-page navigation buttons can use switch_page().
    st.session_state[QUESTIONNAIRE_PAGE_KEY] = questionnaire_page
    st.session_state[ACBC_BYO_PAGE_KEY] = byo_page
    st.session_state[ACBC_SCREENER_PAGE_KEY] = screener_page
    st.session_state[ACBC_TOURNAMENT_PAGE_KEY] = tournament_page
    st.session_state[ACBC_SUMMARY_PAGE_KEY] = summary_page

    st.navigation(
        {
            "Survey": [
                intro_page,
                questionnaire_page,
                byo_page,
                screener_page,
                tournament_page,
                summary_page,
            ]
        }
    ).run()


main()
