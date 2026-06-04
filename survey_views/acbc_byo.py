"""Step 1 of the conjoint survey — pick the favourite level per feature.

Respondent-facing route. Internally this is the ACBC Build-Your-Own (BYO)
stage; the UI deliberately hides that terminology — respondents see
"Step 1 · Build your ideal" and a sequence of one-question pages.

Behaviour:

1. Load the questionnaire spec, surface one question per active attribute
   (:func:`conjoint.acbc.byo.byo_questions`).
2. Drive the sequential controller with one Step per question.
3. On Finish: derive the anchor profile and persist it in session state
   under :data:`ACBC_ANCHOR_KEY` so Step 2 (Screener) can use it.
"""

from __future__ import annotations

import streamlit as st

from conjoint.acbc import byo as acbc_byo
from conjoint.acbc.byo import ByoQuestion
from conjoint.acbc.design import Profile
from survey_views.navigation import (
    Step,
    get_answer,
    record_answer,
    render_sequence,
    reset_stage,
    stage_answers,
)
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import (
    ACBC_SCREENER_PAGE_KEY,
    RESPONDENT_KEY,
)
from survey_views.theme import apply_base_theme, flow_header, safe_md

STAGE = "acbc_byo"

#: Session-state key for the persisted BYO anchor (:class:`Profile`).
ACBC_ANCHOR_KEY = "acbc_anchor"
#: Session-state flag set when BYO is finished — toggles the summary view.
ACBC_BYO_FINISHED_KEY = "acbc_byo_finished"


def _byo_step(question: ByoQuestion) -> Step:
    """One :class:`Step` rendering a single BYO question."""

    def render() -> bool:
        if question.description:
            st.caption(question.description)
        st.write(question.prompt)

        codes = [code for code, _ in question.levels]
        labels = {code: label for code, label in question.levels}
        previous = get_answer(STAGE, question.attribute)
        default_index = (
            codes.index(previous) if previous in codes else None
        )

        chosen = st.radio(
            "Choose one:",
            options=codes,
            format_func=lambda code: safe_md(labels.get(code, code)),
            index=default_index,
            horizontal=False,
            key=f"acbc_byo__{question.attribute}",
        )
        if chosen is None:
            return False
        record_answer(STAGE, question.attribute, str(chosen))
        return True

    return Step(
        identifier=question.attribute,
        title=attribute_display_name(question.attribute),
        render=render,
    )


def _persist_anchor() -> Profile | None:
    """Build the anchor from current BYO answers and store it in session state."""
    spec = load_spec()
    if spec is None:
        return None
    answers = stage_answers(STAGE)
    typed = {key: str(value) for key, value in answers.items() if value is not None}
    anchor = acbc_byo.byo_to_anchor(typed, spec)
    st.session_state[ACBC_ANCHOR_KEY] = anchor
    return anchor


def render_byo() -> None:
    """Render Step 1 (one question per attribute)."""
    apply_base_theme()

    spec = load_spec()
    if spec is None:
        return
    questions = acbc_byo.byo_questions(spec)
    if not questions:
        st.warning("There are no questions to answer right now.")
        return

    flow_header(
        1,
        3,
        "Build your ideal phone",
        "Pick the option you would most prefer for each feature.",
    )

    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip()
    greeting = f"Hi **{respondent}** — there " if respondent else "There "
    st.caption(f"{greeting}are {len(questions)} quick questions, one feature at a time.")

    st.session_state.setdefault(ACBC_BYO_FINISHED_KEY, False)

    def on_complete() -> None:
        _persist_anchor()
        st.session_state[ACBC_BYO_FINISHED_KEY] = True

    if not st.session_state[ACBC_BYO_FINISHED_KEY]:
        steps = tuple(_byo_step(q) for q in questions)
        render_sequence(
            STAGE, steps, on_complete=on_complete, progress_label="Question"
        )

    if st.session_state[ACBC_BYO_FINISHED_KEY]:
        anchor = st.session_state.get(ACBC_ANCHOR_KEY)
        if anchor is None:
            anchor = _persist_anchor()

        st.success("Thanks! Here is the ideal phone you described.")
        if anchor is not None:
            labels = level_label_map(spec)
            with st.container(border=True):
                for attribute, code in anchor.levels:
                    st.markdown(
                        f"- **{attribute_display_name(attribute)}**: "
                        f"{format_level(labels, attribute, code)}"
                    )

        screener_page = st.session_state.get(ACBC_SCREENER_PAGE_KEY)
        cols = st.columns(2)
        with cols[0]:
            if screener_page is not None and st.button("Continue →", type="primary"):
                st.switch_page(screener_page)
        with cols[1]:
            if st.button("Start over"):
                st.session_state[ACBC_BYO_FINISHED_KEY] = False
                st.session_state.pop(ACBC_ANCHOR_KEY, None)
                reset_stage(STAGE)
                st.rerun()


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_byo()
