"""Standalone Streamlit app for creating survey-question workbooks.

This app is intentionally separate from the respondent-facing ``survey.py``.
It only collects the product noun, six Section C feature ids, and editable
prompts, then saves a timestamped ``Survey_questions`` workbook.

Launch with::

    streamlit run survey_setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from survey_views.feature_setup import render_feature_setup  # noqa: E402


def main() -> None:
    """Run the standalone survey setup page."""
    st.set_page_config(
        page_title="Survey question setup",
        page_icon=":material/edit_note:",
        layout="centered",
    )
    render_feature_setup()


if __name__ == "__main__":
    main()
