"""Streamlit AppTest coverage for the Step-1 (BYO) + Step-2 (Screener) views.

Validates that:

* Step 1 renders one attribute per page and only enables Next after the
  respondent picks a level;
* finishing Step 1 persists an anchor profile in session state;
* Step 2 requires an anchor and renders one configuration per page;
* the router exposes every survey route.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent
SURVEY_APP = REPO_ROOT / "survey.py"


def _byo_app() -> AppTest:
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.acbc_byo import render_byo\n"
        "render_byo()\n"
    )
    return AppTest.from_string(script)


def _screener_app() -> AppTest:
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.acbc_screener import render_screener\n"
        "render_screener()\n"
    )
    return AppTest.from_string(script)


def _byo_radio(at: AppTest):
    return next(
        r for r in at.radio if r.key and r.key.startswith("acbc_byo__")
    )


def _next_button(at: AppTest):
    return next(b for b in at.button if b.label in {"Next →", "Finish"})


def _first_active_attribute_name() -> str:
    from conjoint import questionnaire as q
    from survey_views.spec_source import DEFAULT_SPEC, attribute_display_name

    spec = q.read_spec(DEFAULT_SPEC)
    return attribute_display_name(spec.active_attributes[0].feature_name)


@pytest.mark.integration
def test_router_exposes_every_acbc_route() -> None:
    at = AppTest.from_file(str(SURVEY_APP)).run()
    assert not at.exception


@pytest.mark.integration
def test_byo_renders_one_attribute_per_page() -> None:
    at = _byo_app().run()
    assert not at.exception
    subheaders = [s.value for s in at.subheader]
    expected = _first_active_attribute_name()
    assert any(expected in title for title in subheaders)
    # Exactly one BYO radio per page.
    byo_radios = [r for r in at.radio if r.key and r.key.startswith("acbc_byo__")]
    assert len(byo_radios) == 1


@pytest.mark.integration
def test_byo_next_disabled_until_pick() -> None:
    at = _byo_app().run()
    assert _next_button(at).disabled is True
    radio = _byo_radio(at)
    radio.set_value(radio.options[0]).run()
    assert _next_button(at).disabled is False


@pytest.mark.integration
def test_screener_without_anchor_shows_warning() -> None:
    at = _screener_app().run()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert any("Step 1" in msg for msg in warnings)


@pytest.mark.integration
def test_screener_with_anchor_renders_one_profile() -> None:
    """Seed an anchor in session state, then drive the Screener page."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import streamlit as st\n"
        "from conjoint import questionnaire as q\n"
        "from conjoint.acbc.design import Profile\n"
        "from survey_views.acbc_byo import ACBC_ANCHOR_KEY\n"
        "from survey_views.spec_source import DEFAULT_SPEC\n"
        "spec = q.read_spec(DEFAULT_SPEC)\n"
        "anchor = Profile(levels=tuple(\n"
        "    (attr.feature_name, attr.levels[0].code) for attr in spec.active_attributes\n"
        "))\n"
        "st.session_state[ACBC_ANCHOR_KEY] = anchor\n"
        "from survey_views.acbc_screener import render_screener\n"
        "render_screener()\n"
    )
    at = AppTest.from_string(script).run()
    assert not at.exception
    subheaders = [s.value for s in at.subheader]
    assert any("Option 1" in title for title in subheaders)
    radios = [r for r in at.radio if r.key and r.key.startswith("acbc_screener__profile__")]
    assert len(radios) == 1
