"""Resolve a :class:`QuestionnaireSpec` for the survey app.

The survey ships with a committed ``questionnaire_spec.json`` (generated from
``conjoint_demo.xlsx`` via ``python -m conjoint.generate_questionnaire``), so it
works out of the box. A sidebar selector lets a facilitator instead generate the
spec on the fly from any uploaded workbook that carries an ``Edited`` +
``Feature_data`` sheet.

All non-trivial logic lives in :mod:`conjoint.questionnaire`; this module is the
thin Streamlit-facing adapter.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from conjoint import questionnaire as q
from conjoint.questionnaire import QuestionnaireSpec

#: Repo root (this file lives in ``<root>/survey_views/``).
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = ROOT / "questionnaire_spec.json"

_BUNDLED_LABEL = "Bundled spec (questionnaire_spec.json)"
_WORKBOOK_LABEL = "Generate from a workbook"


@st.cache_data(show_spinner=False)
def _spec_dict_from_workbook(workbook_bytes: bytes, name: str) -> dict:
    """Build a spec dict from uploaded workbook bytes (cached by content)."""
    suffix = Path(name).suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(workbook_bytes)
        tmp_path = Path(handle.name)
    try:
        spec = q.build_questionnaire(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return q.spec_to_dict(spec)


def load_spec() -> QuestionnaireSpec | None:
    """Resolve a questionnaire spec from the sidebar source selector.

    Returns ``None`` (after rendering a warning/info) when no usable source is
    available yet, so callers can early-return.
    """
    st.sidebar.header("Questionnaire source")
    source = st.sidebar.radio(
        "Load the questionnaire from",
        (_BUNDLED_LABEL, _WORKBOOK_LABEL),
    )

    if source == _BUNDLED_LABEL:
        spec_path = st.sidebar.text_input("Spec path", value=str(DEFAULT_SPEC))
        if not Path(spec_path).exists():
            st.warning(
                f"No spec found at `{spec_path}`. Generate one with "
                "`python -m conjoint.generate_questionnaire --excel <wb> "
                "--out questionnaire_spec.json`, or switch to "
                "*Generate from a workbook* in the sidebar."
            )
            return None
        return q.read_spec(spec_path)

    uploaded = st.sidebar.file_uploader("Workbook (.xlsx)", type=["xlsx"])
    if uploaded is None:
        st.info("Upload a workbook with an `Edited` + `Feature_data` sheet to begin.")
        return None
    return q.spec_from_dict(
        _spec_dict_from_workbook(uploaded.getvalue(), uploaded.name)
    )
