"""Final "Thank you" route — clean confirmation + optional response download.

This is the last page of the conjoint survey. It hides every analysis
detail (stage names, long-format dataframe, validator messages) and only
shows a short confirmation. A small "Send my responses" button lets the
respondent hand the recorded answers to the researcher as a single CSV.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from conjoint.acbc import byo as acbc_byo
from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.design import (
    Profile,
    attribute_levels_from_spec,
)
from survey_views.acbc_byo import ACBC_ANCHOR_KEY, STAGE as STAGE_BYO_KEY
from survey_views.acbc_screener import ACBC_SCREENER_RESPONSES_KEY
from survey_views.navigation import stage_answers
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import RESPONDENT_KEY
from survey_views.theme import apply_base_theme


def _combined_frame(respondent: str) -> pd.DataFrame:
    """Build the long-format frame from every stage in session state."""
    spec = load_spec()
    if spec is None:
        return pd.DataFrame()
    attribute_levels = attribute_levels_from_spec(spec)

    frames: list[pd.DataFrame] = []

    byo_answers = stage_answers(STAGE_BYO_KEY)
    if byo_answers:
        byo_records = acbc_byo.byo_to_responses(
            {key: str(value) for key, value in byo_answers.items() if value is not None},
            respondent=respondent,
            spec=spec,
        )
        if byo_records:
            frames.append(
                acbc_responses.assemble_byo_responses(byo_records, attribute_levels)
            )

    screener_records = st.session_state.get(ACBC_SCREENER_RESPONSES_KEY, ()) or ()
    if screener_records:
        screener_records = tuple(
            acbc_responses.ScreenerResponse(
                respondent=respondent,
                task_id=r.task_id,
                profile=r.profile,
                accepted=r.accepted,
            )
            for r in screener_records
        )
        frames.append(
            acbc_responses.assemble_screener_responses(screener_records, attribute_levels)
        )

    finalised = st.session_state.get("acbc_summary_frames")
    if finalised:
        frames.extend(finalised)

    if not frames:
        return pd.DataFrame()
    return acbc_responses.concat_responses(*frames)


def record_tournament_frame(frame: pd.DataFrame) -> None:
    """Public hook for the Tournament view to publish its frame.

    The Tournament page already knows the tasks; on Finish it should
    call this so this page can include those rows in the merged CSV.
    """
    bucket = st.session_state.setdefault("acbc_summary_frames", [])
    bucket.append(frame)


def _ideal_configuration(anchor: Profile | None) -> None:
    """Render a friendly recap of the Step-1 picks (level labels, not codes)."""
    if anchor is None:
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
            "It looks like you haven't completed the survey yet — please go "
            "back to Step 1 from the sidebar."
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
