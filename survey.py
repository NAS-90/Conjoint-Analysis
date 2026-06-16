"""Standalone conjoint survey app — its own ``st.navigation`` router.

Decoupled from the analysis dashboard (``app.py``): a respondent opens this
app on its own URL and works through **one linear questionnaire**, modelled on
the Part A / Part B (B0–B5) / Part C structure of the reference design.

Launch with::

    streamlit run survey.py        # or: ./run.sh survey

Routes (rendered in the sidebar nav, grouped under "Survey", in order):

* **Welcome** — instructions + respondent id (:mod:`survey_views.intro`).
* **Part A · About you** — screening / background profiling
  (:mod:`survey_views.part_a_background`).
* **B0 · About the features** — attribute & level explanation
  (:mod:`survey_views.b0_features`).
* **B1 · Rate the features** — per-level desirability
  (:mod:`survey_views.ratings`).
* **B2 · Deal-breakers** — must-have / unacceptable level constraints
  (:mod:`survey_views.b2_constraints`); derives the ideal anchor.
* **B4 · Compare phones** — pair (2-up) choice tasks
  (:mod:`survey_views.acbc_tournament`).
* **B5 · Would you buy it?** — 0–5 purchase-probability calibration
  (:mod:`survey_views.b5_calibration`).
* **Part C · Paying extra** — willingness-to-pay
  (:mod:`survey_views.part_c_wtp`).
* **Thank you** — merged responses CSV (:mod:`survey_views.acbc_summary`).

B3 (importance-of-difference) is intentionally not built yet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # allow ``streamlit run survey.py`` from anywhere
    sys.path.insert(0, str(ROOT))

from survey_views.acbc_summary import render_summary  # noqa: E402
from survey_views.acbc_tournament import render_tournament  # noqa: E402
from survey_views.b0_features import render_features_intro  # noqa: E402
from survey_views.b2_constraints import render_constraints  # noqa: E402
from survey_views.b5_calibration import render_calibration  # noqa: E402
from survey_views.intro import render_intro  # noqa: E402
from survey_views.part_a_background import render_background  # noqa: E402
from survey_views.part_c_wtp import render_wtp  # noqa: E402
from survey_views.ratings import render_questionnaire  # noqa: E402
from survey_views.state import (  # noqa: E402
    ACBC_SUMMARY_PAGE_KEY,
    ACBC_TOURNAMENT_PAGE_KEY,
    B0_PAGE_KEY,
    B2_PAGE_KEY,
    B5_PAGE_KEY,
    PART_A_PAGE_KEY,
    PART_C_PAGE_KEY,
    QUESTIONNAIRE_PAGE_KEY,
)


def ordered_pages(
    *,
    intro,
    part_a,
    b0,
    b1,
    b2,
    b4,
    b5,
    part_c,
    summary,
) -> list:
    """The fixed linear page order for the questionnaire.

    Kept as a pure function so the order can be unit-tested without a running
    app. There is no longer a mode gate — everyone takes the same flow.
    """
    return [intro, part_a, b0, b1, b2, b4, b5, part_c, summary]


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
    part_a_page = st.Page(
        render_background,
        title="About you",
        icon=":material/person:",
        url_path="about-you",
    )
    b0_page = st.Page(
        render_features_intro,
        title="About the features",
        icon=":material/menu_book:",
        url_path="features",
    )
    questionnaire_page = st.Page(
        render_questionnaire,
        title="Rate the features",
        icon=":material/star:",
        url_path="ratings",
    )
    b2_page = st.Page(
        render_constraints,
        title="Deal-breakers",
        icon=":material/rule:",
        url_path="deal-breakers",
    )
    tournament_page = st.Page(
        render_tournament,
        title="Compare phones",
        icon=":material/balance:",
        url_path="compare",
    )
    b5_page = st.Page(
        render_calibration,
        title="Would you buy it?",
        icon=":material/shopping_cart:",
        url_path="would-you-buy",
    )
    part_c_page = st.Page(
        render_wtp,
        title="Paying extra",
        icon=":material/payments:",
        url_path="paying-extra",
    )
    summary_page = st.Page(
        render_summary,
        title="Thank you",
        icon=":material/check_circle:",
        url_path="thank-you",
    )

    # Stash page handles so each section's Next/Finish can switch_page() to the
    # following section.
    st.session_state[PART_A_PAGE_KEY] = part_a_page
    st.session_state[B0_PAGE_KEY] = b0_page
    st.session_state[QUESTIONNAIRE_PAGE_KEY] = questionnaire_page
    st.session_state[B2_PAGE_KEY] = b2_page
    st.session_state[ACBC_TOURNAMENT_PAGE_KEY] = tournament_page
    st.session_state[B5_PAGE_KEY] = b5_page
    st.session_state[PART_C_PAGE_KEY] = part_c_page
    st.session_state[ACBC_SUMMARY_PAGE_KEY] = summary_page

    pages = ordered_pages(
        intro=intro_page,
        part_a=part_a_page,
        b0=b0_page,
        b1=questionnaire_page,
        b2=b2_page,
        b4=tournament_page,
        b5=b5_page,
        part_c=part_c_page,
        summary=summary_page,
    )

    st.navigation({"Survey": pages}).run()


if __name__ == "__main__":
    main()
