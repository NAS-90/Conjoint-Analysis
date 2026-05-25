"""Streamlit page — collect Part B-1 conjoint ratings and export responses.csv.

This is a thin Streamlit multipage view. All non-trivial logic lives in
:mod:`conjoint.questionnaire` / :mod:`conjoint.io` so it stays testable:

* the spec is loaded from a ``questionnaire_spec.json`` (or generated on the fly
  from a chosen workbook via :func:`conjoint.questionnaire.build_questionnaire`);
* each active Part B-1 attribute renders one 1..5 rating ``number_input`` per
  level (the desirability scale, algorithm_spec.md §2);
* on submit the answers are assembled with
  :func:`conjoint.questionnaire.responses_from_answers` and offered as a
  ``responses.csv`` download that feeds ``python -m conjoint.estimate``.

Run via the dashboard's multipage nav (``./run.sh app``) or directly with
``streamlit run pages/questionnaire.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow ``streamlit run pages/questionnaire.py``
    sys.path.insert(0, str(ROOT))

from conjoint import questionnaire as q  # noqa: E402  (import after sys.path bootstrap)
from conjoint.questionnaire import QuestionnaireSpec  # noqa: E402

DEFAULT_SPEC = ROOT / "questionnaire_spec.json"


@st.cache_data(show_spinner=False)
def _spec_from_workbook(workbook_bytes: bytes, name: str) -> dict:
    """Build a spec dict from uploaded workbook bytes (cached by content)."""
    tmp = ROOT / f".uploaded_{name}"
    tmp.write_bytes(workbook_bytes)
    try:
        spec = q.build_questionnaire(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return q.spec_to_dict(spec)


def _load_spec() -> QuestionnaireSpec | None:
    """Resolve a questionnaire spec from the sidebar source selector."""
    st.sidebar.header("Questionnaire source")
    source = st.sidebar.radio(
        "Load the questionnaire from",
        ("questionnaire_spec.json", "Generate from a workbook"),
    )

    if source == "questionnaire_spec.json":
        spec_path = st.sidebar.text_input(
            "Spec path", value=str(DEFAULT_SPEC)
        )
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
    return q.spec_from_dict(_spec_from_workbook(uploaded.getvalue(), uploaded.name))


def _render_questions(spec: QuestionnaireSpec) -> dict[str, int]:
    """Render the active B-1 rating questions; return {column: rating}."""
    answers: dict[str, int] = {}
    scale = spec.scale
    default = (scale.min + scale.max) // 2
    for attr in spec.active_attributes:
        st.subheader(attr.feature_name)
        if attr.description:
            st.caption(attr.description)
        st.write(attr.prompt)
        for level in attr.levels:
            column = q.response_column(attr.feature_name, level.code)
            answers[column] = st.number_input(
                f"{level.label} ({level.code})",
                min_value=int(scale.min),
                max_value=int(scale.max),
                value=int(default),
                step=1,
                key=column,
            )
    return answers


def main() -> None:
    st.set_page_config(page_title="Conjoint questionnaire", layout="centered")
    st.title("Conjoint questionnaire — Part B-1 ratings")

    spec = _load_spec()
    if spec is None:
        return

    active = spec.active_attributes
    if not active:
        st.warning("This spec has no active Part B-1 rating attributes.")
        return

    st.caption(
        f"{len(active)} attribute(s), rating scale "
        f"{spec.scale.min}–{spec.scale.max}. Higher = more desirable."
    )

    respondent = st.text_input("Respondent id", value="1")
    answers = _render_questions(spec)

    if st.button("Build responses.csv"):
        frame = q.responses_from_answers(
            [answers], spec, respondent_ids=[respondent or "1"]
        )
        problems = q.validate_responses(frame, spec)
        if problems:
            st.error("Response validation failed:")
            for problem in problems:
                st.write(f"- {problem}")
            return
        st.success("Responses look valid. Download below and feed to `conjoint.estimate`.")
        st.dataframe(frame, width="stretch")
        st.download_button(
            "Download responses.csv",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name="responses.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
else:  # pragma: no cover - executed when Streamlit imports the page module
    main()
