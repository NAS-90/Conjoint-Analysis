"""Step 2 of the conjoint survey — accept-or-reject candidate configurations.

Respondent-facing route. Internally this is the ACBC Screener: a small pool
of profiles is generated around the Step-1 anchor and the respondent says
Yes/No to each one. The UI hides that terminology and any design-control
widgets — defaults are picked here so the respondent only sees questions.

On Finish, the accepted profiles (plus the anchor) are stashed under
:data:`ACBC_SURVIVORS_KEY` so Step 3 (Tournament) uses them as its profile
pool.
"""

from __future__ import annotations

import streamlit as st

from conjoint.acbc import screener as acbc_screener
from conjoint.acbc.design import (
    Profile,
    attribute_levels_from_spec,
)
from conjoint.acbc.responses import ScreenerResponse
from survey_views.acbc_byo import ACBC_ANCHOR_KEY
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
    ACBC_BYO_PAGE_KEY,
    ACBC_TOURNAMENT_PAGE_KEY,
    RESPONDENT_KEY,
)
from survey_views.theme import apply_base_theme, flow_header

STAGE = "acbc_screener"

#: Session-state key for the survivor pool consumed by the Tournament.
ACBC_SURVIVORS_KEY = "acbc_screener_survivors"
#: Session-state key for the full list of ScreenerResponses collected.
ACBC_SCREENER_RESPONSES_KEY = "acbc_screener_responses"
#: Session-state flag toggled when the Screener has finished.
ACBC_SCREENER_FINISHED_KEY = "acbc_screener_finished"

#: Fixed defaults chosen so respondents never see design knobs.
_SCREENER_SEED = 2026


def _screener_step(
    task_id: int, profile: Profile, labels: dict[str, dict[str, str]]
) -> Step:
    """One :class:`Step` rendering a single Screener profile."""

    def render() -> bool:
        st.caption(
            "Would you consider this configuration if it were available?"
        )
        with st.container(border=True):
            for attribute, code in profile.levels:
                st.markdown(
                    f"- **{attribute_display_name(attribute)}**: "
                    f"{format_level(labels, attribute, code)}"
                )

        previous = get_answer(STAGE, str(task_id))
        options = ["Yes", "No"]
        index = options.index(previous) if previous in options else None
        chosen = st.radio(
            "Your answer:",
            options=options,
            index=index,
            horizontal=True,
            key=f"acbc_screener__profile__{task_id}",
        )
        if chosen is None:
            return False
        record_answer(STAGE, str(task_id), chosen)
        return True

    return Step(
        identifier=f"profile_{task_id}",
        title=f"Option {task_id}",
        render=render,
    )


def _collected_responses(
    respondent: object, profiles: tuple[Profile, ...]
) -> tuple[ScreenerResponse, ...]:
    """Materialise the answers into :class:`ScreenerResponse` records."""
    answers = stage_answers(STAGE)
    records: list[ScreenerResponse] = []
    for index, profile in enumerate(profiles, start=1):
        answer = answers.get(str(index))
        if answer is None:
            continue
        records.append(
            acbc_screener.screener_response_record(
                respondent=respondent,
                task_id=index,
                profile=profile,
                accepted=str(answer).lower() == "yes",
            )
        )
    return tuple(records)


def render_screener() -> None:
    """Render Step 2 (one configuration per page)."""
    apply_base_theme()

    spec = load_spec()
    if spec is None:
        return

    flow_header(
        2,
        3,
        "Would you consider these options?",
        "For each example option, tell us whether you would consider buying it.",
    )

    anchor = st.session_state.get(ACBC_ANCHOR_KEY)
    if anchor is None:
        st.warning(
            "Please answer Step 1 first so we can tailor the next questions to "
            "your preferences."
        )
        byo_page = st.session_state.get(ACBC_BYO_PAGE_KEY)
        if byo_page is not None and st.button("Go to Step 1 →", type="primary"):
            st.switch_page(byo_page)
        return

    attribute_levels = attribute_levels_from_spec(spec)
    n_profiles = acbc_screener.DEFAULT_SCREENER_POOL
    max_changes = min(acbc_screener.DEFAULT_MAX_CHANGES, len(attribute_levels))

    try:
        profiles = acbc_screener.seed_screener_pool(
            anchor,
            attribute_levels,
            n_profiles=n_profiles,
            max_changes=max_changes,
            seed=_SCREENER_SEED,
        )
    except ValueError:
        st.error("We could not prepare the next questions. Please try again later.")
        return

    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"
    st.caption(f"{len(profiles)} example options, one per screen.")

    st.session_state.setdefault(ACBC_SCREENER_FINISHED_KEY, False)

    def on_complete() -> None:
        responses = _collected_responses(respondent, profiles)
        survivors = list(acbc_screener.filter_survivors(responses, threshold=1))
        if not any(profile.levels == anchor.levels for profile in survivors):
            survivors.insert(0, anchor)
        st.session_state[ACBC_SURVIVORS_KEY] = tuple(survivors)
        st.session_state[ACBC_SCREENER_RESPONSES_KEY] = responses
        st.session_state[ACBC_SCREENER_FINISHED_KEY] = True

    if not st.session_state[ACBC_SCREENER_FINISHED_KEY]:
        labels = level_label_map(spec)
        steps = tuple(
            _screener_step(i + 1, p, labels) for i, p in enumerate(profiles)
        )
        render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Option")

    if st.session_state[ACBC_SCREENER_FINISHED_KEY]:
        responses = st.session_state.get(ACBC_SCREENER_RESPONSES_KEY, ())
        accepted = sum(1 for r in responses if r.accepted)
        st.success(
            f"Thanks! You said *yes* to {accepted} of {len(responses)} "
            "configurations — they will be used in the final step."
        )

        tournament_page = st.session_state.get(ACBC_TOURNAMENT_PAGE_KEY)
        cols = st.columns(2)
        with cols[0]:
            if tournament_page is not None and st.button("Continue →", type="primary"):
                st.switch_page(tournament_page)
        with cols[1]:
            if st.button("Start over"):
                st.session_state[ACBC_SCREENER_FINISHED_KEY] = False
                st.session_state.pop(ACBC_SURVIVORS_KEY, None)
                st.session_state.pop(ACBC_SCREENER_RESPONSES_KEY, None)
                reset_stage(STAGE)
                st.rerun()


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_screener()
