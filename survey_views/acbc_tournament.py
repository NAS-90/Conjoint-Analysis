"""Step 3 of the conjoint survey — pick a favourite from a small set.

Respondent-facing route. Internally this is the ACBC Tournament; the UI
hides that terminology and the design-control widgets. Each page shows a
few configurations side-by-side and the respondent picks one.

The Tournament uses one of two profile pools (auto-detected):

1. The Step-2 accepted configurations stashed by
   :mod:`survey_views.acbc_screener` under
   :data:`survey_views.acbc_screener.ACBC_SURVIVORS_KEY`.
2. A freshly-generated balanced pool drawn from the active attributes (the
   fallback when Step 2 was skipped).

On Finish, the long-format response frame is published to
:mod:`survey_views.acbc_summary` so the final "Thank you" page can offer it
to the researcher as a CSV.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.design import (
    Profile,
    attribute_levels_from_spec,
    generate_profiles,
)
from conjoint.acbc.tournament import Task, build_tasks
from conjoint.questionnaire import QuestionnaireSpec
from survey_views.acbc_byo import ACBC_ANCHOR_KEY
from survey_views.acbc_screener import ACBC_SURVIVORS_KEY
from survey_views.navigation import (
    Step,
    get_answer,
    record_answer,
    render_sequence,
    reset_stage,
)
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import (
    ACBC_SUMMARY_PAGE_KEY,
    RESPONDENT_KEY,
)
from survey_views.theme import apply_base_theme, flow_header

STAGE = "acbc_tournament"

#: Fixed defaults so respondents never see design knobs.
_DEFAULT_TASKS = 8
_DEFAULT_ALTS_PER_TASK = 3
_DEFAULT_SEED = 2026
#: Balanced design pool used only when Step 2 (Screener) was skipped.
_FALLBACK_POOL_SIZE = 24
#: Smallest survivor pool we will run a Tournament on; below this we top up
#: with fresh balanced profiles so there is always a varied comparison.
_MIN_TOURNAMENT_POOL = 8

FINISHED_KEY = "acbc_tournament_finished"


# ---------------------------------------------------------------------------
# Cached design generation
# ---------------------------------------------------------------------------
def _resolve_pool(
    spec: QuestionnaireSpec,
    *,
    min_pool: int,
    fallback_pool: int,
    seed: int,
) -> tuple[Profile, ...]:
    """Profile pool for the Tournament.

    Prefers the Step-2 survivors (the configurations the respondent said they
    would consider, plus their Step-1 ideal). Two safety nets keep the stage
    from breaking on real data:

    * **Step 2 skipped** (no survivors) → a fresh balanced design pool, which
      :func:`conjoint.acbc.tournament.build_tasks` partitions exactly as before.
    * **Very few survivors** (accepted almost nothing) → top up with extra
      balanced profiles so there is always a varied comparison to show. This,
      with the relaxed ``build_tasks``, is what unblocks Screener → Tournament.
    """
    survivors = list(st.session_state.get(ACBC_SURVIVORS_KEY) or ())
    anchor = st.session_state.get(ACBC_ANCHOR_KEY)
    if anchor is not None and anchor not in survivors:
        survivors.insert(0, anchor)

    if not survivors:
        return generate_profiles(spec, n_profiles=fallback_pool, seed=seed)

    pool: list[Profile] = list(survivors)
    if len(pool) < min_pool:
        seen = {profile.levels for profile in pool}
        for extra in generate_profiles(spec, n_profiles=min_pool * 2, seed=seed):
            if extra.levels in seen:
                continue
            seen.add(extra.levels)
            pool.append(extra)
            if len(pool) >= min_pool:
                break
    return tuple(pool)


def _generate_tasks(
    pool: tuple[Profile, ...], *, n_tasks: int, alts: int, seed: int
) -> tuple[Task, ...]:
    """Build Tournament tasks from a profile pool (deterministic in ``seed``)."""
    return build_tasks(pool, n_tasks=n_tasks, alts_per_task=alts, seed=seed)


def _format_profile(
    profile: Profile, labels: dict[str, dict[str, str]]
) -> str:
    """Markdown bullet list of ``attribute: level`` lines using human labels."""
    return "\n".join(
        f"- **{attribute_display_name(attribute)}**: "
        f"{format_level(labels, attribute, code)}"
        for attribute, code in profile.levels
    )


# ---------------------------------------------------------------------------
# Single-task step renderer
# ---------------------------------------------------------------------------
def _task_step(task: Task, labels: dict[str, dict[str, str]]) -> Step:
    """Build a :class:`Step` for a single Tournament task."""

    def render() -> bool:
        st.caption(
            "Of the options below, which would you most prefer if these were "
            "the only choices available?"
        )
        columns = st.columns(len(task.alternatives))
        for index, (column, profile) in enumerate(zip(columns, task.alternatives)):
            with column:
                with st.container(border=True):
                    st.markdown(f"#### Option {chr(ord('A') + index)}")
                    st.markdown(_format_profile(profile, labels))

        prior = get_answer(STAGE, str(task.task_id))
        options = list(range(len(task.alternatives)))
        button_labels = [f"Option {chr(ord('A') + i)}" for i in options]
        try:
            default_index = options.index(int(prior)) if prior is not None else None
        except (TypeError, ValueError):
            default_index = None

        chosen = st.radio(
            "Your choice:",
            options=options,
            format_func=lambda i: button_labels[i],
            index=default_index,
            horizontal=True,
            key=f"acbc_tournament__task__{task.task_id}",
        )
        if chosen is None:
            return False
        record_answer(STAGE, str(task.task_id), int(chosen))
        return True

    return Step(
        identifier=f"task_{task.task_id}",
        title=f"Question {task.task_id}",
        render=render,
    )


# ---------------------------------------------------------------------------
# Finish: assemble and publish to the summary page
# ---------------------------------------------------------------------------
def _assemble_frame(
    spec: QuestionnaireSpec, tasks: tuple[Task, ...]
) -> tuple[pd.DataFrame, list[str]]:
    """Long-format frame for the recorded answers + any validator problems."""
    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"
    answers = []
    for task in tasks:
        chosen = get_answer(STAGE, str(task.task_id))
        if chosen is None:
            continue
        answers.append(
            acbc_responses.TournamentResponse(
                respondent=respondent, task=task, chosen_index=int(chosen)
            )
        )
    attribute_levels = attribute_levels_from_spec(spec)
    frame = acbc_responses.assemble_tournament_responses(answers, attribute_levels)
    problems = acbc_responses.validate_acbc_responses(frame, attribute_levels)
    return frame, problems


def _publish_to_summary(frame: pd.DataFrame) -> None:
    """Replace any prior Tournament frame in the summary bucket."""
    from survey_views.acbc_summary import record_tournament_frame

    bucket = st.session_state.setdefault("acbc_summary_frames", [])
    non_tournament = [
        existing
        for existing in bucket
        if acbc_responses.STAGE_COL in existing.columns
        and acbc_responses.STAGE_TOURNAMENT
        not in existing[acbc_responses.STAGE_COL].unique()
    ]
    st.session_state["acbc_summary_frames"] = non_tournament
    record_tournament_frame(frame)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def render_tournament() -> None:
    """Render Step 3 (one question per page)."""
    apply_base_theme()

    spec = load_spec()
    if spec is None:
        return
    if not spec.active_attributes:
        st.warning("There are no configurations to compare right now.")
        return

    flow_header(
        3,
        3,
        "Pick your favourite",
        "Choose the phone you would most prefer in each comparison.",
    )

    try:
        pool = _resolve_pool(
            spec,
            min_pool=_MIN_TOURNAMENT_POOL,
            fallback_pool=_FALLBACK_POOL_SIZE,
            seed=_DEFAULT_SEED,
        )
        n_tasks = max(1, min(_DEFAULT_TASKS, len(pool)))
        tasks = _generate_tasks(
            pool,
            n_tasks=n_tasks,
            alts=_DEFAULT_ALTS_PER_TASK,
            seed=_DEFAULT_SEED,
        )
    except ValueError:
        st.error("We could not prepare the comparison questions. Please try again later.")
        return

    st.caption(f"{len(tasks)} comparisons, one per screen.")

    st.session_state.setdefault(FINISHED_KEY, False)

    def on_complete() -> None:
        st.session_state[FINISHED_KEY] = True

    if not st.session_state[FINISHED_KEY]:
        labels = level_label_map(spec)
        steps = tuple(_task_step(task, labels) for task in tasks)
        render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Question")

    if st.session_state[FINISHED_KEY]:
        frame, problems = _assemble_frame(spec, tasks)
        if problems:
            st.error("Sorry — we couldn't record your answers. Please try again.")
            if st.button("Start over"):
                st.session_state[FINISHED_KEY] = False
                reset_stage(STAGE)
                st.rerun()
            return

        if not frame.empty:
            _publish_to_summary(frame)

        st.success("Thanks! That was the last question.")
        summary_page = st.session_state.get(ACBC_SUMMARY_PAGE_KEY)
        cols = st.columns(2)
        with cols[0]:
            if summary_page is not None and st.button("Finish →", type="primary"):
                st.switch_page(summary_page)
        with cols[1]:
            if st.button("Start over"):
                st.session_state[FINISHED_KEY] = False
                reset_stage(STAGE)
                st.rerun()


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_tournament()
