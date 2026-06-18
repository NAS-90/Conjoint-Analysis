"""Tests for the B4 (pair comparison) Streamlit view + router integration.

Drives ``survey_views.acbc_tournament.render_tournament`` through
``streamlit.testing.v1.AppTest`` to verify:

* the page renders one *pair* (two concepts) at a time with Back/Next chrome;
* completing every comparison publishes the long-format choice frame for the
  summary page;
* the concept pool honours the respondent's B2 unacceptable constraints;
* the survey.py router runs with the single linear flow (no mode toggle).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent
SURVEY_APP = REPO_ROOT / "survey.py"

_NEXT_LABELS = {"Next →", "Finish"}


def _tournament_app() -> AppTest:
    """An ``AppTest`` running the B4 view stand-alone."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.acbc_tournament import render_tournament\n"
        "render_tournament()\n"
    )
    return AppTest.from_string(script)


def _anchored_app() -> AppTest:
    """B4 seeded with an iOS anchor and an 'never Android' B2 constraint."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import streamlit as st\n"
        "from conjoint import questionnaire as q\n"
        "from conjoint.acbc.design import Profile\n"
        "from survey_views.spec_source import DEFAULT_SPEC\n"
        "from survey_views.state import ACBC_ANCHOR_KEY, UNACCEPTABLE_KEY\n"
        "spec = q.read_spec(DEFAULT_SPEC)\n"
        "anchor = Profile(levels=tuple(\n"
        "    (a.feature_name, ('ios' if a.feature_name == 'os' else a.levels[0].code))\n"
        "    for a in spec.active_attributes\n"
        "))\n"
        "st.session_state[ACBC_ANCHOR_KEY] = anchor\n"
        "st.session_state[UNACCEPTABLE_KEY] = {'os': {'android'}}\n"
        "from survey_views.acbc_tournament import render_tournament\n"
        "render_tournament()\n"
    )
    return AppTest.from_string(script)


def _task_radio(at: AppTest):
    return next(r for r in at.radio if r.key and r.key.startswith("acbc_tournament__task__"))


def _next_button(at: AppTest):
    return next(b for b in at.button if b.label in _NEXT_LABELS)


def _finish(at: AppTest) -> None:
    """Answer every comparison (always pick Option A) until the last Finish."""
    for _ in range(20):
        radios = [
            r for r in at.radio if r.key and r.key.startswith("acbc_tournament__task__")
        ]
        if not radios:
            break
        radios[0].set_value(0).run()
        nxt = next((b for b in at.button if b.label in _NEXT_LABELS), None)
        if nxt is None:
            break
        was_finish = nxt.label == "Finish"
        nxt.click().run()
        if was_finish:
            break


@pytest.mark.integration
def test_router_runs_with_linear_flow() -> None:
    """The survey.py router runs and Welcome has no mode toggle."""
    at = AppTest.from_file(str(SURVEY_APP)).run()
    assert not at.exception
    assert not at.radio  # the quick-Rating mode chooser was removed
    assert any(b.label.startswith("Start") for b in at.button)


@pytest.mark.integration
def test_tournament_renders_one_pair_per_page() -> None:
    at = _tournament_app().run()
    assert not at.exception
    subheaders = [s.value for s in at.subheader]
    assert any("Comparison 1" in title for title in subheaders)
    # Exactly one choice radio per page...
    task_radios = [r for r in at.radio if r.key and r.key.startswith("acbc_tournament__task__")]
    assert len(task_radios) == 1
    # ...and it is a *pair* — two options.
    assert len(task_radios[0].options) == 2


@pytest.mark.integration
def test_tournament_next_disabled_until_choice() -> None:
    at = _tournament_app().run()
    assert _next_button(at).disabled is True
    _task_radio(at).set_value(0).run()
    assert _next_button(at).disabled is False


@pytest.mark.integration
def test_finishing_tournament_publishes_choice_frame() -> None:
    at = _tournament_app().run()
    _finish(at)

    assert not at.exception
    assert "acbc_summary_frames" in at.session_state
    frames = at.session_state["acbc_summary_frames"]
    assert frames, "B4 should publish a choice frame on finish"
    frame = frames[-1]
    assert (frame["stage"] == "tournament").all()
    # Pairs → alternative_index is only ever 0 or 1.
    assert set(frame["alternative_index"].unique()) <= {0, 1}
    # Exactly one chosen alternative per task.
    assert frame.groupby("task_id")["chosen"].sum().eq(1).all()


@pytest.mark.integration
def test_tournament_respects_unacceptable_constraint() -> None:
    """No concept may carry a B2-unacceptable level (here: Android)."""
    at = _anchored_app().run()
    assert not at.exception
    _finish(at)

    frame = at.session_state["acbc_summary_frames"][-1]
    assert (frame["os=level"] != "android").all()
    assert (frame["os=level"] == "ios").all()
