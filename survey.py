"""Standalone conjoint survey app — its own ``st.navigation`` router.

Decoupled from the analysis dashboard (``app.py``): a respondent opens this app
on its own URL, fills in Part B-1 ratings and downloads ``responses.csv``.

Launch with::

    streamlit run survey.py        # or: ./run.sh survey

Routes (rendered in the sidebar nav, grouped under "Survey"):

* **Welcome** — instructions + respondent id (:mod:`survey_views.intro`).
* **Part B-1 ratings** — the desirability questionnaire
  (:mod:`survey_views.ratings`); on submit it builds + validates a downloadable
  ``responses.csv`` via :mod:`conjoint.questionnaire`.

The view code lives in :mod:`survey_views`; this entry point only wires the
router together.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # allow ``streamlit run survey.py`` from anywhere
    sys.path.insert(0, str(ROOT))

from survey_views.intro import render_intro  # noqa: E402  (after sys.path bootstrap)
from survey_views.ratings import render_questionnaire  # noqa: E402
from survey_views.state import QUESTIONNAIRE_PAGE_KEY  # noqa: E402


def main() -> None:
    """Configure the page and run the survey navigation router."""
    st.set_page_config(page_title="Conjoint survey", page_icon="📝", layout="centered")

    intro_page = st.Page(
        render_intro, title="Welcome", icon="👋", url_path="welcome", default=True
    )
    questionnaire_page = st.Page(
        render_questionnaire, title="Part B-1 ratings", icon="📝", url_path="ratings"
    )
    # Stash the ratings page so the intro's "Start" button can switch to it.
    st.session_state[QUESTIONNAIRE_PAGE_KEY] = questionnaire_page

    st.navigation({"Survey": [intro_page, questionnaire_page]}).run()


main()
