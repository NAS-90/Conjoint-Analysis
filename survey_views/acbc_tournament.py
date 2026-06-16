"""B4 — pair comparison / choice tasks (the core of the conjoint).

Each screen shows **two** complete phone concepts and the respondent picks the
one they prefer in a realistic trade-off. This is the core choice data behind
part-worth utilities and attribute importance.

The concepts are drawn from a pool built around the respondent's derived ideal
(the anchor from B1 + B2), filtered to honour their B2 constraints — so every
concept is one they could plausibly consider. On Finish the long-format choice
frame is published to :mod:`survey_views.acbc_summary` for the merged CSV and the
flow advances to B5 (calibration).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from conjoint.acbc import responses as acbc_responses
from conjoint.acbc.constraints import anchor_from_ratings, filter_by_constraints
from conjoint.acbc.design import (
    Profile,
    attribute_levels_from_spec,
    generate_profiles,
)
from conjoint.acbc.screener import seed_screener_pool
from conjoint.acbc.tournament import Task, build_tasks
from conjoint.questionnaire import QuestionnaireSpec
from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    peek_stage,
    record_answer,
    render_sequence,
)
from survey_views.ratings import STAGE as RATINGS_STAGE
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import (
    ACBC_ANCHOR_KEY,
    B5_PAGE_KEY,
    MUST_HAVE_KEY,
    RESPONDENT_KEY,
    UNACCEPTABLE_KEY,
)
from survey_views.theme import apply_base_theme, flow_header

STAGE = "acbc_tournament"

#: Fixed defaults so respondents never see design knobs. B4 is a *pair*
#: comparison (two concepts per screen), per the reference design.
_DEFAULT_TASKS = 8
_DEFAULT_ALTS_PER_TASK = 2
_DEFAULT_SEED = 2026
#: Target pool size — ≥ ``_DEFAULT_TASKS * _DEFAULT_ALTS_PER_TASK`` lets
#: :func:`build_tasks` use disjoint pairs (partition mode).
_TARGET_POOL = 16


# ---------------------------------------------------------------------------
# Profile pool (ratings-anchor + B2 constraints)
# ---------------------------------------------------------------------------
def _resolve_anchor(spec: QuestionnaireSpec, must_have, unacceptable) -> Profile:
    """The session anchor (from B2), or one freshly derived from B1 ratings."""
    anchor = st.session_state.get(ACBC_ANCHOR_KEY)
    if isinstance(anchor, Profile):
        return anchor
    return anchor_from_ratings(
        peek_stage(RATINGS_STAGE), spec, must_have=must_have, unacceptable=unacceptable
    )


def _resolve_pool(spec: QuestionnaireSpec, *, target: int, seed: int) -> tuple[Profile, ...]:
    """Constraint-valid concept pool centred on the respondent's ideal.

    Combines near-anchor perturbations with a balanced design, keeps only
    profiles that satisfy the B2 constraints, and (as a safety net for very
    tight constraints) tops up with a few unfiltered balanced profiles so a
    pair can always be shown.
    """
    must_have = st.session_state.get(MUST_HAVE_KEY, {}) or {}
    unacceptable = st.session_state.get(UNACCEPTABLE_KEY, {}) or {}
    anchor = _resolve_anchor(spec, must_have, unacceptable)
    attribute_levels = attribute_levels_from_spec(spec)

    seen = {anchor.levels}
    pool: list[Profile] = [anchor]

    try:
        perturbed = seed_screener_pool(
            anchor,
            attribute_levels,
            n_profiles=target * 2,
            max_changes=min(3, len(attribute_levels)),
            seed=seed,
        )
    except ValueError:
        perturbed = ()
    balanced = generate_profiles(spec, n_profiles=target * 3, seed=seed)

    for profile in filter_by_constraints(
        [*perturbed, *balanced], must_have=must_have, unacceptable=unacceptable
    ):
        if profile.levels in seen:
            continue
        seen.add(profile.levels)
        pool.append(profile)
        if len(pool) >= target:
            break

    floor = _DEFAULT_ALTS_PER_TASK * 2
    if len(pool) < floor:  # constraints left too few — relax to keep pairs showable
        for profile in balanced:
            if profile.levels in seen:
                continue
            seen.add(profile.levels)
            pool.append(profile)
            if len(pool) >= floor:
                break
    return tuple(pool)


def _format_profile(profile: Profile, labels: dict[str, dict[str, str]]) -> str:
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
    """Build a :class:`Step` for a single pair-comparison task."""

    def render() -> bool:
        st.caption(
            "Of the two phones below, which would you choose if these were your "
            "only options?"
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
        title=f"Comparison {task.task_id}",
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
    """Render B4 (one pair comparison per screen)."""
    apply_base_theme()

    spec = load_spec()
    if spec is None:
        return
    if not spec.active_attributes:
        st.warning("There are no configurations to compare right now.")
        return

    flow_header(
        5,
        7,
        "Compare phones",
        "Choose the phone you would prefer in each side-by-side comparison.",
    )

    try:
        pool = _resolve_pool(spec, target=_TARGET_POOL, seed=_DEFAULT_SEED)
        n_tasks = max(1, min(_DEFAULT_TASKS, len(pool)))
        tasks = build_tasks(
            pool,
            n_tasks=n_tasks,
            alts_per_task=_DEFAULT_ALTS_PER_TASK,
            seed=_DEFAULT_SEED,
        )
    except ValueError:
        st.error("We could not prepare the comparison questions. Please try again later.")
        return

    st.caption(f"{len(tasks)} comparisons, one per screen.")

    labels = level_label_map(spec)
    steps = tuple(_task_step(task, labels) for task in tasks)

    def on_complete() -> None:
        frame, problems = _assemble_frame(spec, tasks)
        if problems:
            st.error("Sorry — we couldn't record your answers. Please try again.")
            return
        if not frame.empty:
            _publish_to_summary(frame)
        advance_to(B5_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Comparison")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_tournament()
