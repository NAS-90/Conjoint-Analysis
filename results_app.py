"""Standalone Streamlit entry point for the ACBC results dashboard.

Run it directly (separate from ``app.py``)::

    SURVEY_SPEC=questionnaire_spec_computers.json \
    SURVEY_WORKBOOK=computer_survey_questions.xlsx \
        streamlit run results_app.py

It loads a long-format ``acbc_responses.csv`` (or generates a synthetic one),
fits MNL + Hierarchical Bayes, and presents attribute importance, part-worth
utilities, willingness-to-pay, a market simulator, purchase likelihood and
respondent segments. All rendering lives in
:func:`dashboard.results_dashboard.render_results_dashboard` so it stays
importable and unit-testable.
"""

from __future__ import annotations

import streamlit as st

from dashboard.results_dashboard import render_results_dashboard

st.set_page_config(page_title="ACBC 调研结果 / Conjoint Results", layout="wide")

render_results_dashboard()
