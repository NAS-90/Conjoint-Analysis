"""Final "Thank you" route — confirmation + merged response download.

The last page of the questionnaire. It hides every analysis detail and shows a
short confirmation plus a single "Send my responses" button that hands the
researcher one CSV. That CSV merges every section the respondent completed —
Part A background, B2 must-have/unacceptable, B4 choices, B5 calibration and
Part C WTP — in the long format defined by :mod:`conjoint.acbc.responses`.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.design import Profile, attribute_levels_from_spec
from survey_views.b5_calibration import CALIBRATION_CONCEPTS_KEY
from survey_views.b5_calibration import STAGE as CALIBRATION_STAGE
from survey_views.navigation import peek_stage
from survey_views.part_a_background import STAGE as BACKGROUND_STAGE
from survey_views.part_c_wtp import STAGE as WTP_STAGE
from survey_views.section_source import (
    load_background_questions,
    load_wtp_features,
)
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import (
    ACBC_ANCHOR_KEY,
    MUST_HAVE_KEY,
    RESPONDENT_KEY,
    UNACCEPTABLE_KEY,
)
from survey_views.theme import apply_base_theme


def _background_frame(respondent: str, attribute_levels) -> pd.DataFrame | None:
    answers = peek_stage(BACKGROUND_STAGE)
    records = []
    for task_id, question in enumerate(load_background_questions(), start=1):
        value = answers.get(question.identifier)
        if value in (None, "", []):
            continue
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(item) for item in value)
        records.append(
            acbc_responses.BackgroundResponse(
                respondent, task_id, question.identifier, str(value)
            )
        )
    if not records:
        return None
    return acbc_responses.assemble_background_responses(records, attribute_levels)


def _musthave_frame(respondent: str, attribute_levels) -> pd.DataFrame | None:
    must_have = st.session_state.get(MUST_HAVE_KEY, {}) or {}
    unacceptable = st.session_state.get(UNACCEPTABLE_KEY, {}) or {}
    records = []
    task_id = 0
    for attribute, level in must_have.items():
        task_id += 1
        records.append(
            acbc_responses.ConstraintResponse(
                respondent, task_id, attribute, level, "must_have"
            )
        )
    for attribute, levels in unacceptable.items():
        for level in levels:
            task_id += 1
            records.append(
                acbc_responses.ConstraintResponse(
                    respondent, task_id, attribute, level, "unacceptable"
                )
            )
    if not records:
        return None
    return acbc_responses.assemble_musthave_responses(records, attribute_levels)


def _calibration_frame(respondent: str, attribute_levels) -> pd.DataFrame | None:
    concepts = st.session_state.get(CALIBRATION_CONCEPTS_KEY, ()) or ()
    answers = peek_stage(CALIBRATION_STAGE)
    records = []
    for index, profile in enumerate(concepts):
        probability = answers.get(str(index))
        if probability is None:
            continue
        records.append(
            acbc_responses.CalibrationResponse(
                respondent, index + 1, profile, int(probability)
            )
        )
    if not records:
        return None
    return acbc_responses.assemble_calibration_responses(records, attribute_levels)


def _wtp_frame(respondent: str, attribute_levels) -> pd.DataFrame | None:
    answers = peek_stage(WTP_STAGE)
    records = []
    for task_id, feature in enumerate(load_wtp_features(), start=1):
        answer = answers.get(feature.identifier)
        if answer in (None, ""):
            continue
        records.append(
            acbc_responses.WtpResponse(respondent, task_id, feature.identifier, str(answer))
        )
    if not records:
        return None
    return acbc_responses.assemble_wtp_responses(records, attribute_levels)


def _combined_frame(respondent: str) -> pd.DataFrame:
    """Merge every completed section into one long-format frame."""
    spec = load_spec()
    if spec is None:
        return pd.DataFrame()
    attribute_levels = attribute_levels_from_spec(spec)

    frames: list[pd.DataFrame] = []
    for frame in (
        _background_frame(respondent, attribute_levels),
        _musthave_frame(respondent, attribute_levels),
    ):
        if frame is not None and not frame.empty:
            frames.append(frame)

    # B4 choice frames are published into this bucket by the Tournament page.
    frames.extend(st.session_state.get("acbc_summary_frames", []) or [])

    for frame in (
        _calibration_frame(respondent, attribute_levels),
        _wtp_frame(respondent, attribute_levels),
    ):
        if frame is not None and not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return acbc_responses.concat_responses(*frames)


def record_tournament_frame(frame: pd.DataFrame) -> None:
    """Public hook for the Tournament view to publish its frame."""
    bucket = st.session_state.setdefault("acbc_summary_frames", [])
    bucket.append(frame)


def _ideal_configuration(anchor: Profile | None) -> None:
    """Render a friendly recap of the derived ideal (level labels, not codes)."""
    if not isinstance(anchor, Profile):
        return
    spec = load_spec()
    if spec is None:
        return
    labels = level_label_map(spec)
    with st.expander("Your ideal configuration", expanded=False):
        for attribute, code in anchor.levels:
            st.markdown(
                f"- **{attribute_display_name(attribute)}**: "
                f"{format_level(labels, attribute, code)}"
            )


def render_summary() -> None:
    """Render the final 'Thank you' page."""
    apply_base_theme()
    st.title("All done — thank you!")
    st.markdown(
        "<p class='lead'>Your answers have been recorded. You can close this "
        "window now, or send your responses to the researcher below.</p>",
        unsafe_allow_html=True,
    )

    spec = load_spec()
    if spec is None:
        return
    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"

    frame = _combined_frame(respondent)
    if frame.empty:
        st.info(
            "It looks like you haven't completed the survey yet — please start "
            "from the Welcome page in the sidebar."
        )
        return

    st.progress(1.0, text="Survey complete")
    _ideal_configuration(st.session_state.get(ACBC_ANCHOR_KEY))

    with st.container(border=True):
        st.markdown("##### Send your responses")
        st.caption(
            "This downloads a single file with your answers for the researcher to analyse."
        )
        st.download_button(
            "Send my responses to the researcher",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=f"responses_{respondent}.csv",
            mime="text/csv",
            type="primary",
        )


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_summary()
