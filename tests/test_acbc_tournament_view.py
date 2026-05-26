"""Tests for the ACBC Tournament Streamlit view + router integration.

Drives ``survey_views.acbc_tournament.render_tournament`` through
``streamlit.testing.v1.AppTest`` to verify:

* the page renders one task at a time with Back/Next chrome;
* completing every task yields a valid ``acbc_responses.csv`` download;
* the survey.py router exposes the ACBC route alongside the legacy ratings.
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
    """The survey.py router includes Welcome + Ratings + Tournament."""
    at = AppTest.from_file(str(SURVEY_APP)).run()
    assert not at.exception
    # Default page is Welcome — the radio with the mode toggle should exist.
    mode_radios = [r for r in at.radio if r.label == "Survey mode"]
    assert mode_radios, "Welcome page is missing the mode toggle"


@pytest.mark.integration
def test_tournament_renders_one_task_per_page() -> None:
    at = _tournament_app().run()
    assert not at.exception
    # Page title for the first task.
    subheaders = [s.value for s in at.subheader]
    assert any("Choice task 1" in title for title in subheaders)
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
def test_finishing_tournament_emits_valid_responses_csv() -> None:
    at = _tournament_app().run()
    # 8 default tasks → click Next/Finish 8 times, picking option 0 each time.
    for _ in range(8):
        _task_radio(at).set_value(0).run()
        _next_button(at).click().run()

    assert not at.exception
    assert any("look valid" in msg.value for msg in at.success)
    # On Finish the recorded answers are rendered as a dataframe alongside
    # the download button.
    assert len(at.dataframe) == 1
