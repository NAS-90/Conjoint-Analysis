"""Sequential page controller for the survey app.

This module decouples the *how do we render N steps one-at-a-time* concern
from the per-stage UI code. A stage (rating flow, BYO, screener, tournament)
declares its ``Step`` sequence; this module owns step navigation in
``st.session_state`` and renders the surrounding chrome (progress bar +
Back/Next buttons).

The single-page-per-question UX in the linear Part A / B / C sections, and the
ACBC BYO / Screener / Tournament views added in later phases, all run on top of
this controller.

The controller is intentionally framework-agnostic about *what* a step
contains. A step is just a callable that renders one page and returns
``True`` when the respondent has produced a valid answer (so ``Next`` can
become enabled). All rating / choice data is stored under
:data:`survey_views.state.STAGE_ANSWERS_KEY` by the step itself, keyed by a
caller-chosen identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st

from survey_views.state import (
    STAGE_ANSWERS_KEY,
    STAGE_KEY,
    STEP_INDEX_KEY,
)

#: A renderer returns ``True`` when the current step's answer is complete.
StepRenderer = Callable[[], bool]


@dataclass(frozen=True)
class Step:
    """One page of a sequential flow.

    ``identifier`` is the slug used in widget keys (``f"{stage}__{step}"``)
    and the lookup key in :data:`STAGE_ANSWERS_KEY`. ``title`` is shown above
    the renderer; ``render`` is the per-page UI callback.
    """

    identifier: str
    title: str
    render: StepRenderer


# ---------------------------------------------------------------------------
# Session-state helpers
# ---------------------------------------------------------------------------
def _ensure_stage(stage: str) -> None:
    """Initialise the stage / step-index / answers slots for ``stage``.

    Each stage owns its own answer dict so flows can be re-entered without
    bleeding data across stages. Resetting the step index when the active
    stage changes keeps the Back/Next pointer aligned with the new flow.
    """
    if st.session_state.get(STAGE_KEY) != stage:
        st.session_state[STAGE_KEY] = stage
        st.session_state[STEP_INDEX_KEY] = 0
    st.session_state.setdefault(STAGE_ANSWERS_KEY, {})
    answers = st.session_state[STAGE_ANSWERS_KEY]
    answers.setdefault(stage, {})


def stage_answers(stage: str) -> dict[str, object]:
    """Return the (mutable) answer dict for ``stage`` (auto-initialised).

    Side effect: makes ``stage`` the *active* stage (resetting the step pointer
    if it changed). Only call it for the stage a page is currently driving — to
    read *another* stage's answers from inside a page, use :func:`peek_stage`,
    which has no side effects.
    """
    _ensure_stage(stage)
    return st.session_state[STAGE_ANSWERS_KEY][stage]


def peek_stage(stage: str) -> dict[str, object]:
    """Read ``stage``'s answers without touching the active-stage / step pointer.

    Unlike :func:`stage_answers`, this never calls :func:`_ensure_stage`, so it
    is safe to read a *different* stage's answers from inside a view that drives
    :func:`render_sequence` (reading another stage via ``stage_answers`` would
    reset that view's step index to 0 on every rerun).
    """
    answers = st.session_state.get(STAGE_ANSWERS_KEY, {}) or {}
    return answers.get(stage, {}) or {}


def record_answer(stage: str, identifier: str, value: object) -> None:
    """Persist ``value`` under ``stage[identifier]`` (replacing any prior)."""
    stage_answers(stage)[identifier] = value


def get_answer(stage: str, identifier: str, default: object = None) -> object:
    """Return the previously recorded answer (or ``default``)."""
    return stage_answers(stage).get(identifier, default)


def current_step_index(stage: str, total_steps: int) -> int:
    """Clamped step pointer for ``stage`` (always inside ``[0, total_steps)``)."""
    _ensure_stage(stage)
    index = int(st.session_state.get(STEP_INDEX_KEY, 0))
    if total_steps <= 0:
        return 0
    return max(0, min(index, total_steps - 1))


def reset_stage(stage: str) -> None:
    """Wipe ``stage``'s answers + step pointer (used to restart a flow)."""
    st.session_state[STAGE_KEY] = stage
    st.session_state[STEP_INDEX_KEY] = 0
    answers = st.session_state.setdefault(STAGE_ANSWERS_KEY, {})
    answers[stage] = {}


def advance_to(page_key: str) -> None:
    """Switch to the :class:`st.Page` stashed under ``page_key``.

    No-op when the handle is missing (e.g. a page opened standalone in a test),
    so callers can use it unconditionally as a section's "Next/Finish" action.
    """
    page = st.session_state.get(page_key)
    if page is not None:
        st.switch_page(page)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_progress(label: str, completed: int, total: int) -> None:
    """Render a top-of-page progress bar (``completed/total`` with label)."""
    if total <= 0:
        return
    fraction = max(0.0, min(1.0, completed / total))
    st.progress(fraction, text=f"{label}: {completed}/{total}")


def render_sequence(
    stage: str,
    steps: tuple[Step, ...],
    *,
    on_complete: Callable[[], None] | None = None,
    progress_label: str = "Progress",
) -> None:
    """Render the current step of ``stage`` with Back/Next chrome.

    The controller is deliberately tiny:

    1. Resolve the current step index, clamped to ``[0, len(steps))``.
    2. Draw a progress bar above the page so the respondent always knows how
       far they are.
    3. Render the step title + the step's own UI, capturing whether the
       answer is complete.
    4. Draw Back (disabled on the first page) and Next/Finish buttons; on
       Next, advance the index (or, on the last page, call ``on_complete``).
    """
    if not steps:
        st.info("No questions to show.")
        return

    index = current_step_index(stage, len(steps))
    step = steps[index]

    render_progress(progress_label, index, len(steps))
    st.subheader(step.title)
    answered = bool(step.render())

    back_col, _, next_col = st.columns([1, 4, 1])
    with back_col:
        if st.button(
            "← Back",
            key=f"{stage}__back__{index}",
            disabled=index == 0,
        ):
            st.session_state[STEP_INDEX_KEY] = max(0, index - 1)
            st.rerun()

    is_last = index == len(steps) - 1
    with next_col:
        label = "Finish" if is_last else "Next →"
        if st.button(
            label,
            key=f"{stage}__next__{index}",
            type="primary",
            disabled=not answered,
        ):
            if is_last:
                if on_complete is not None:
                    on_complete()
            else:
                st.session_state[STEP_INDEX_KEY] = index + 1
                st.rerun()
