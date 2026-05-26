"""ACBC summary route — combine BYO + Screener + Tournament downloads.

This is the "thank you" page at the end of the ACBC flow. It shows the
answers from each stage that lives in session state and offers the
respondent the merged ``acbc_responses.csv`` (long-format,
:data:`STAGE` column distinguishes BYO / Screener / Tournament rows).
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
from conjoint.acbc.responses import (
    TournamentResponse,
)
from survey_views.acbc_byo import ACBC_ANCHOR_KEY, STAGE as STAGE_BYO_KEY
from survey_views.acbc_screener import ACBC_SCREENER_RESPONSES_KEY
from survey_views.navigation import stage_answers
from survey_views.spec_source import load_spec
from survey_views.state import RESPONDENT_KEY


def _combined_frame(respondent: str) -> pd.DataFrame:
    """Build the long-format frame from every ACBC stage in session state."""
    spec = load_spec()
    if spec is None:
        return pd.DataFrame()
    attribute_levels = attribute_levels_from_spec(spec)

    frames: list[pd.DataFrame] = []

    # BYO -----------------------------------------------------------------
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

    # Screener ------------------------------------------------------------
    screener_records = st.session_state.get(ACBC_SCREENER_RESPONSES_KEY, ()) or ()
    if screener_records:
        # Respondent on the dataclass is whoever filled the Screener — we
        # rewrite it here so the file uses a single respondent id.
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

    # Tournament ----------------------------------------------------------
    tournament_state = stage_answers("acbc_tournament")
    if tournament_state:
        anchor: Profile | None = st.session_state.get(ACBC_ANCHOR_KEY)
        # We don't have the original tasks here, but the Tournament view
        # itself emits the long-format frame at finish-time. The summary
        # page just stitches whatever has been stored.
        pass

    finalised = st.session_state.get("acbc_summary_frames")
    if finalised:
        frames.extend(finalised)

    if not frames:
        return pd.DataFrame()
    return acbc_responses.concat_responses(*frames)


def record_tournament_frame(frame: pd.DataFrame) -> None:
    """Public hook for the Tournament view to publish its frame.

    The Tournament page already knows the tasks; on Finish it should
    call this so the summary route can include those rows in the
    merged CSV.
    """
    bucket = st.session_state.setdefault("acbc_summary_frames", [])
    bucket.append(frame)


def render_summary() -> None:
    """Render the ACBC summary / download page."""
    st.title("ACBC summary")

    spec = load_spec()
    if spec is None:
        return
    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"

    frame = _combined_frame(respondent)
    if frame.empty:
        st.info(
            "No ACBC answers in this session yet — finish at least one of "
            "BYO / Screener / Tournament to populate this page."
        )
        return

    by_stage = frame.groupby(acbc_responses.STAGE_COL).size().to_dict()
    summary_pieces = [f"{count} {stage} row(s)" for stage, count in by_stage.items()]
    st.success("Stages captured · " + ", ".join(summary_pieces))
    st.dataframe(frame, width="stretch")

    st.download_button(
        "Download acbc_responses.csv",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name="acbc_responses.csv",
        mime="text/csv",
    )


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_summary()
