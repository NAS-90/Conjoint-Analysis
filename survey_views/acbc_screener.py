"""ACBC Screener route — Yes/No on BYO-anchored profile pool.

Drives one Screener profile per page via the sequential navigation
controller. The pool is generated from the BYO anchor that
:mod:`survey_views.acbc_byo` left in session state under
``ACBC_ANCHOR_KEY``; if the anchor is missing the page asks the
respondent to complete BYO first.

On Finish, the surviving profiles (Yes votes) plus the BYO anchor are
stashed under :data:`ACBC_SURVIVORS_KEY` so the Tournament can use
them as its profile pool.
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
from survey_views.spec_source import load_spec
from survey_views.state import (
    ACBC_BYO_PAGE_KEY,
    ACBC_TOURNAMENT_PAGE_KEY,
    RESPONDENT_KEY,
)

STAGE = "acbc_screener"

#: Session-state key for the survivor pool consumed by the Tournament.
ACBC_SURVIVORS_KEY = "acbc_screener_survivors"
#: Session-state key for the full list of ScreenerResponses collected.
ACBC_SCREENER_RESPONSES_KEY = "acbc_screener_responses"
#: Session-state flag toggled when the Screener has finished.
ACBC_SCREENER_FINISHED_KEY = "acbc_screener_finished"

SCREENER_SEED_KEY = "acbc_screener_seed"


def _screener_step(task_id: int, profile: Profile) -> Step:
    """One :class:`Step` rendering a single Screener profile."""

    def render() -> bool:
        st.caption(
            "Would you consider this configuration if it were available?"
        )
        with st.container(border=True):
            for attribute, code in profile.levels:
                st.markdown(f"- **{attribute}**: {code}")

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
        title=f"Profile {task_id}",
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
    """Render the ACBC Screener route (one profile per page)."""
    st.title("ACBC Screener — would you consider these?")

    spec = load_spec()
    if spec is None:
        return
    anchor = st.session_state.get(ACBC_ANCHOR_KEY)
    if anchor is None:
        st.warning(
            "No BYO anchor in session — finish the BYO route first so we can "
            "generate Screener profiles."
        )
        byo_page = st.session_state.get(ACBC_BYO_PAGE_KEY)
        if byo_page is not None and st.button("Go to BYO →", type="primary"):
            st.switch_page(byo_page)
        return

    attribute_levels = attribute_levels_from_spec(spec)
    with st.sidebar:
        st.header("ACBC Screener")
        seed = int(
            st.number_input(
                "Random seed", min_value=0, value=2026, step=1, key=SCREENER_SEED_KEY
            )
        )
        n_profiles = int(
            st.number_input(
                "Profiles to show",
                min_value=3,
                max_value=24,
                value=acbc_screener.DEFAULT_SCREENER_POOL,
                step=1,
            )
        )
        max_changes = int(
            st.number_input(
                "Max attributes flipped per profile",
                min_value=1,
                max_value=max(1, len(attribute_levels)),
                value=min(acbc_screener.DEFAULT_MAX_CHANGES, len(attribute_levels)),
                step=1,
            )
        )

    try:
        profiles = acbc_screener.seed_screener_pool(
            anchor,
            attribute_levels,
            n_profiles=n_profiles,
            max_changes=max_changes,
            seed=seed,
        )
    except ValueError as exc:
        st.error(f"Could not seed Screener pool: {exc}")
        return

    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"
    st.caption(
        f"Respondent **{respondent}** · {len(profiles)} candidate profiles · "
        f"≤ {max_changes} flips from your BYO anchor."
    )

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
        steps = tuple(_screener_step(i + 1, p) for i, p in enumerate(profiles))
        render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Profile")
        return

    survivors = st.session_state.get(ACBC_SURVIVORS_KEY, ()) or ()
    responses = st.session_state.get(ACBC_SCREENER_RESPONSES_KEY, ())

    accepted = sum(1 for r in responses if r.accepted)
    st.success(
        f"Screener recorded: {accepted}/{len(responses)} accepted · "
        f"{len(survivors)} profiles (incl. BYO anchor) go into the Tournament."
    )

    if survivors:
        with st.expander("Survivors", expanded=False):
            for profile in survivors:
                st.markdown(", ".join(f"**{a}** = {c}" for a, c in profile.levels))

    tournament_page = st.session_state.get(ACBC_TOURNAMENT_PAGE_KEY)
    cols = st.columns(2)
    with cols[0]:
        if tournament_page is not None and st.button("Continue to Tournament →", type="primary"):
            st.switch_page(tournament_page)
    with cols[1]:
        if st.button("Restart Screener"):
            st.session_state[ACBC_SCREENER_FINISHED_KEY] = False
            st.session_state.pop(ACBC_SURVIVORS_KEY, None)
            st.session_state.pop(ACBC_SCREENER_RESPONSES_KEY, None)
            reset_stage(STAGE)
            st.rerun()


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_screener()
