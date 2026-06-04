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
from survey_views.intro import MODE_RATING, render_intro  # noqa: E402
from survey_views.ratings import render_questionnaire  # noqa: E402
from survey_views.state import (  # noqa: E402
    ACBC_BYO_PAGE_KEY,
    ACBC_SCREENER_PAGE_KEY,
    ACBC_SUMMARY_PAGE_KEY,
    ACBC_TOURNAMENT_PAGE_KEY,
    QUESTIONNAIRE_PAGE_KEY,
    SURVEY_MODE_KEY,
)


def flow_pages(
    mode: str | None,
    *,
    intro,
    questionnaire,
    byo,
    screener,
    tournament,
    summary,
) -> list:
    """Ordered sidebar pages for the chosen survey ``mode`` (gating logic).

    Welcome is always first. The rating method shows only the ratings page;
    every other mode (including the unset default) shows the ACBC flow. Kept as
    a pure function so the gating can be unit-tested without a running app.
    """
    if mode == MODE_RATING:
        return [intro, questionnaire]
    return [intro, byo, screener, tournament, summary]


def main() -> None:
    """Configure the page and run the survey navigation router."""
    st.set_page_config(
        page_title="Smartphone preferences survey",
        page_icon=":material/smartphone:",
        layout="centered",
    )

    intro_page = st.Page(
        render_intro,
        title="Welcome",
        icon=":material/home:",
        url_path="welcome",
        default=True,
    )
    questionnaire_page = st.Page(
        render_questionnaire,
        title="Rate each option",
        icon=":material/star:",
        url_path="ratings",
    )
    byo_page = st.Page(
        render_byo,
        title="Step 1 · Your ideal",
        icon=":material/tune:",
        url_path="acbc-byo",
    )
    screener_page = st.Page(
        render_screener,
        title="Step 2 · Would you consider these?",
        icon=":material/checklist:",
        url_path="acbc-screener",
    )
    tournament_page = st.Page(
        render_tournament,
        title="Step 3 · Final choice",
        icon=":material/balance:",
        url_path="acbc-tournament",
    )
    summary_page = st.Page(
        render_summary,
        title="Thank you",
        icon=":material/check_circle:",
        url_path="acbc-summary",
    )

    # Stash page handles so cross-page navigation buttons can use switch_page().
    st.session_state[QUESTIONNAIRE_PAGE_KEY] = questionnaire_page
    st.session_state[ACBC_BYO_PAGE_KEY] = byo_page
    st.session_state[ACBC_SCREENER_PAGE_KEY] = screener_page
    st.session_state[ACBC_TOURNAMENT_PAGE_KEY] = tournament_page
    st.session_state[ACBC_SUMMARY_PAGE_KEY] = summary_page

    # Gate the sidebar to the chosen method so respondents only ever see the
    # flow they picked on Welcome (no out-of-order jumps, no clutter). The mode
    # is set by the Welcome radio, which reruns the script before "Start" is
    # pressed, so st.switch_page always targets a page in the current nav.
    pages = flow_pages(
        st.session_state.get(SURVEY_MODE_KEY),
        intro=intro_page,
        questionnaire=questionnaire_page,
        byo=byo_page,
        screener=screener_page,
        tournament=tournament_page,
        summary=summary_page,
    )

    st.navigation({"Survey": pages}).run()


if __name__ == "__main__":
    main()
