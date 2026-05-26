"""ACBC Tournament route — single-page-per-choice-task UI.

Renders one Tournament choice task per page using
:func:`survey_views.navigation.render_sequence`. The respondent sees
``alts_per_task`` profile "cards" side-by-side and picks one. On Finish
the assembled responses are validated against
:mod:`conjoint.acbc.responses` and offered as a downloadable
``acbc_responses.csv``.

The Tournament uses a profile pool generated up-front from the active
Part B-1 attributes (via :mod:`conjoint.acbc.design`). BYO + Screener
(Phase 3) will refine the pool; this view runs even without them.
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
from survey_views.navigation import (
    Step,
    get_answer,
    record_answer,
    render_sequence,
    reset_stage,
)
from survey_views.spec_source import load_spec
from survey_views.state import RESPONDENT_KEY

STAGE = "acbc_tournament"

DEFAULT_POOL_SIZE = 24
DEFAULT_TASKS = 8
DEFAULT_ALTS_PER_TASK = 3
SEED_KEY = "acbc_tournament_seed"
FINISHED_KEY = "acbc_tournament_finished"


# ---------------------------------------------------------------------------
# Cached design generation
# ---------------------------------------------------------------------------
def _generate_tasks(
    spec: QuestionnaireSpec, *, pool_size: int, n_tasks: int, alts: int, seed: int
) -> tuple[Task, ...]:
    """Build Tournament tasks from the active spec (deterministic in ``seed``)."""
    pool = generate_profiles(spec, n_profiles=pool_size, seed=seed)
    return build_tasks(pool, n_tasks=n_tasks, alts_per_task=alts, seed=seed)


def _format_profile(profile: Profile) -> str:
    """Markdown bullet list of ``attribute: level`` lines."""
    return "\n".join(f"- **{attribute}**: {code}" for attribute, code in profile.levels)


# ---------------------------------------------------------------------------
# Single-task step renderer
# ---------------------------------------------------------------------------
def _task_step(task: Task) -> Step:
    """Build a :class:`Step` for a single Tournament task."""

    def render() -> bool:
        st.caption(
            "Pick the option you would most prefer if these were the only choices available."
        )
        columns = st.columns(len(task.alternatives))
        for index, (column, profile) in enumerate(zip(columns, task.alternatives)):
            with column:
                with st.container(border=True):
                    st.markdown(f"#### Option {chr(ord('A') + index)}")
                    st.markdown(_format_profile(profile))

        prior = get_answer(STAGE, str(task.task_id))
        options = list(range(len(task.alternatives)))
        labels = [f"Option {chr(ord('A') + i)}" for i in options]
        try:
            default_index = options.index(int(prior)) if prior is not None else None
        except (TypeError, ValueError):
            default_index = None

        chosen = st.radio(
            "Your choice:",
            options=options,
            format_func=lambda i: labels[i],
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
        title=f"Choice task {task.task_id}",
        render=render,
    )


# ---------------------------------------------------------------------------
# Finish: assemble + validate + download
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


def _offer_download(frame: pd.DataFrame, problems: list[str]) -> None:
    """Render validation results and a download button for the CSV."""
    if problems:
        st.error("Response validation failed:")
        for problem in problems:
            st.write(f"- {problem}")
        return
    st.success(
        "Tournament responses look valid. Download below and feed to "
        "`python -m conjoint.acbc.estimate`."
    )
    st.dataframe(frame, width="stretch")
    st.download_button(
        "Download acbc_responses.csv",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name="acbc_responses.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _design_controls(default_seed: int) -> tuple[int, int, int, int]:
    """Sidebar widgets for tweaking the design + seed (facilitator-facing)."""
    with st.sidebar:
        st.header("ACBC design")
        seed = st.number_input(
            "Random seed", min_value=0, value=default_seed, step=1, key=SEED_KEY
        )
        pool_size = st.number_input(
            "Profile pool size",
            min_value=DEFAULT_ALTS_PER_TASK * 2,
            value=DEFAULT_POOL_SIZE,
            step=1,
        )
        n_tasks = st.number_input(
            "Number of tasks", min_value=1, value=DEFAULT_TASKS, step=1
        )
        alts = st.number_input(
            "Alternatives per task",
            min_value=2,
            max_value=5,
            value=DEFAULT_ALTS_PER_TASK,
            step=1,
        )
    return int(seed), int(pool_size), int(n_tasks), int(alts)


def render_tournament() -> None:
    """Render the ACBC Tournament route (one task per page)."""
    st.title("ACBC Tournament — pick your favourite")

    spec = load_spec()
    if spec is None:
        return
    if not spec.active_attributes:
        st.warning("This spec has no active Part B-1 attributes; nothing to tournament.")
        return

    seed, pool_size, n_tasks, alts = _design_controls(default_seed=2026)

    try:
        tasks = _generate_tasks(spec, pool_size=pool_size, n_tasks=n_tasks, alts=alts, seed=seed)
    except ValueError as exc:
        st.error(f"Could not build choice tasks: {exc}")
        return

    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"
    st.caption(
        f"Respondent **{respondent}** · {len(tasks)} choice tasks · {alts} options each."
    )

    st.session_state.setdefault(FINISHED_KEY, False)

    def on_complete() -> None:
        st.session_state[FINISHED_KEY] = True

    if not st.session_state[FINISHED_KEY]:
        steps = tuple(_task_step(task) for task in tasks)
        render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Task")

    if st.session_state[FINISHED_KEY]:
        frame, problems = _assemble_frame(spec, tasks)
        _offer_download(frame, problems)
        if st.button("Restart Tournament"):
            st.session_state[FINISHED_KEY] = False
            reset_stage(STAGE)
            st.rerun()


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_tournament()
