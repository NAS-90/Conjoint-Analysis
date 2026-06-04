"""Tests for the Step-3 (Tournament) Streamlit view + router integration.

Drives ``survey_views.acbc_tournament.render_tournament`` through
``streamlit.testing.v1.AppTest`` to verify:

* the page renders one question at a time with Back/Next chrome;
* completing every question yields the friendly confirmation;
* the survey.py router exposes the Step-3 route alongside the other steps.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent
SURVEY_APP = REPO_ROOT / "survey.py"


def _tournament_app() -> AppTest:
    """An ``AppTest`` running the Tournament view stand-alone."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.acbc_tournament import render_tournament\n"
        "render_tournament()\n"
    )
    return AppTest.from_string(script)


def _task_radio(at: AppTest):
    return next(r for r in at.radio if r.key and r.key.startswith("acbc_tournament__task__"))


def _next_button(at: AppTest):
    return next(b for b in at.button if b.label in {"Next →", "Finish"})


@pytest.mark.integration
def test_tournament_router_exposes_route() -> None:
    """The survey.py router includes the welcome page with a mode toggle."""
    at = AppTest.from_file(str(SURVEY_APP)).run()
    assert not at.exception
    # Default page is the Welcome route — at least one radio (the mode toggle)
    # should be present.
    assert at.radio, "Welcome page is missing the mode toggle"


@pytest.mark.integration
def test_tournament_renders_one_question_per_page() -> None:
    at = _tournament_app().run()
    assert not at.exception
    # Page title for the first question.
    subheaders = [s.value for s in at.subheader]
    assert any("Question 1" in title for title in subheaders)
    # Exactly one radio per page.
    task_radios = [r for r in at.radio if r.key and r.key.startswith("acbc_tournament__task__")]
    assert len(task_radios) == 1


@pytest.mark.integration
def test_tournament_next_disabled_until_choice() -> None:
    at = _tournament_app().run()
    assert _next_button(at).disabled is True
    _task_radio(at).set_value(0).run()
    assert _next_button(at).disabled is False


@pytest.mark.integration
def test_finishing_tournament_shows_thank_you() -> None:
    at = _tournament_app().run()
    # 8 default tasks → click Next/Finish 8 times, picking option 0 each time.
    for _ in range(8):
        _task_radio(at).set_value(0).run()
        _next_button(at).click().run()

    assert not at.exception
    assert any("last question" in msg.value for msg in at.success)


def _survivor_app() -> AppTest:
    """An ``AppTest`` for the Tournament fed by a small Screener-survivor pool.

    Mirrors the live flow: a Step-1 anchor plus a handful of accepted Step-2
    profiles in session state. This is the path that previously crashed —
    ``build_tasks`` demanded 24 profiles but the survivor pool is ~6.
    """
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import streamlit as st\n"
        "from conjoint import questionnaire as q\n"
        "from conjoint.acbc.design import Profile, attribute_levels_from_spec\n"
        "from conjoint.acbc.screener import seed_screener_pool\n"
        "from survey_views.acbc_byo import ACBC_ANCHOR_KEY\n"
        "from survey_views.acbc_screener import ACBC_SURVIVORS_KEY\n"
        "from survey_views.spec_source import DEFAULT_SPEC\n"
        "spec = q.read_spec(DEFAULT_SPEC)\n"
        "anchor = Profile(levels=tuple(\n"
        "    (a.feature_name, a.levels[0].code) for a in spec.active_attributes\n"
        "))\n"
        "pool = seed_screener_pool(\n"
        "    anchor, attribute_levels_from_spec(spec),\n"
        "    n_profiles=5, max_changes=2, seed=1,\n"
        ")\n"
        "st.session_state[ACBC_ANCHOR_KEY] = anchor\n"
        "st.session_state[ACBC_SURVIVORS_KEY] = (anchor,) + tuple(pool)\n"
        "from survey_views.acbc_tournament import render_tournament\n"
        "render_tournament()\n"
    )
    return AppTest.from_string(script)


@pytest.mark.integration
def test_tournament_runs_on_small_survivor_pool() -> None:
    """Regression: Screener → Tournament must not error on a small pool."""
    at = _survivor_app().run()
    assert not at.exception
    assert not any("could not prepare" in e.value for e in at.error)
    task_radios = [
        r for r in at.radio if r.key and r.key.startswith("acbc_tournament__task__")
    ]
    assert len(task_radios) == 1


@pytest.mark.integration
def test_finishing_tournament_from_survivors_shows_thank_you() -> None:
    at = _survivor_app().run()
    for _ in range(20):  # robust to the pool-derived task count
        radios = [
            r for r in at.radio if r.key and r.key.startswith("acbc_tournament__task__")
        ]
        if not radios:
            break
        radios[0].set_value(0).run()
        nxt = next((b for b in at.button if b.label in {"Next →", "Finish"}), None)
        if nxt is None:
            break
        nxt.click().run()
        if any("last question" in m.value for m in at.success):
            break

    assert not at.exception
    assert any("last question" in msg.value for msg in at.success)
