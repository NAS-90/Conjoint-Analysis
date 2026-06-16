"""Smoke + integration tests for the new linear-flow sections.

Each new section view (Part A, B0, B2, B5, Part C) is rendered stand-alone via
``AppTest`` to confirm it runs and shows its key controls, plus one integration
test that the Thank-you page merges every section into one CSV frame.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _app(render_call: str, preamble: str = "") -> AppTest:
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import streamlit as st\n"
        f"{preamble}"
        f"{render_call}\n"
    )
    return AppTest.from_string(script)


@pytest.mark.integration
def test_part_a_renders_first_question() -> None:
    at = _app(
        "from survey_views.part_a_background import render_background\n"
        "render_background()"
    ).run()
    assert not at.exception
    assert any(r.key == "background__purchase_timing" for r in at.radio)


@pytest.mark.integration
def test_b0_renders_ready_button() -> None:
    at = _app(
        "from survey_views.b0_features import render_features_intro\n"
        "render_features_intro()"
    ).run()
    assert not at.exception
    assert any(b.label.startswith("I'm ready") for b in at.button)


@pytest.mark.integration
def test_b2_renders_constraint_controls() -> None:
    at = _app(
        "from survey_views.b2_constraints import render_constraints\n"
        "render_constraints()"
    ).run()
    assert not at.exception
    # First attribute page exposes a must-have selectbox and a never multiselect.
    assert any(s.key == "musthave__mh__price" for s in at.selectbox)
    assert any(m.key == "musthave__un__price" for m in at.multiselect)


@pytest.mark.integration
def test_b5_renders_probability_radio() -> None:
    at = _app(
        "from survey_views.b5_calibration import render_calibration\n"
        "render_calibration()"
    ).run()
    assert not at.exception
    radio = next((r for r in at.radio if r.key == "calibration__0"), None)
    assert radio is not None
    assert len(radio.options) == 6  # 0..5 inclusive


@pytest.mark.integration
def test_part_c_renders_amount_bands() -> None:
    at = _app(
        "from survey_views.part_c_wtp import render_wtp\n"
        "render_wtp()"
    ).run()
    assert not at.exception
    radio = next((r for r in at.radio if r.key == "wtp__camera"), None)
    assert radio is not None
    assert len(radio.options) == 4


@pytest.mark.integration
def test_summary_merges_every_section_into_one_frame() -> None:
    """The Thank-you page's ``_combined_frame`` covers all completed sections."""
    preamble = (
        "from conjoint import questionnaire as q\n"
        "from conjoint.acbc.design import Profile, attribute_levels_from_spec\n"
        "from conjoint.acbc import responses as r\n"
        "from conjoint.acbc.tournament import build_tasks\n"
        "from survey_views.spec_source import DEFAULT_SPEC\n"
        "from survey_views.state import (\n"
        "    STAGE_ANSWERS_KEY, MUST_HAVE_KEY, UNACCEPTABLE_KEY,\n"
        ")\n"
        "from survey_views.b5_calibration import CALIBRATION_CONCEPTS_KEY\n"
        "spec = q.read_spec(DEFAULT_SPEC)\n"
        "al = attribute_levels_from_spec(spec)\n"
        "first = {a.feature_name: a.levels[0].code for a in spec.active_attributes}\n"
        "anchor = Profile(levels=tuple(first.items()))\n"
        "other = Profile(levels=tuple({**first, 'storage': '256gb'}.items()))\n"
        "st.session_state[STAGE_ANSWERS_KEY] = {\n"
        "    'background': {'purchase_timing': 'Within 3 months',\n"
        "                   'usage': ['Gaming', 'Photography']},\n"
        "    'ratings': {a.feature_name: {lv.code: 3 for lv in a.levels}\n"
        "                for a in spec.active_attributes},\n"
        "    'calibration': {'0': 5, '1': 2},\n"
        "    'wtp': {'camera': 'up_to_100', 'battery': 'none'},\n"
        "}\n"
        "st.session_state[MUST_HAVE_KEY] = {'os': 'ios'}\n"
        "st.session_state[UNACCEPTABLE_KEY] = {'storage': {'64gb'}}\n"
        "st.session_state[CALIBRATION_CONCEPTS_KEY] = (anchor, other)\n"
        "tasks = build_tasks((anchor, other), n_tasks=1, alts_per_task=2, seed=1)\n"
        "tframe = r.assemble_tournament_responses(\n"
        "    [r.TournamentResponse('r1', tasks[0], 0)], al)\n"
        "st.session_state['acbc_summary_frames'] = [tframe]\n"
        "from survey_views.acbc_summary import _combined_frame\n"
        "frame = _combined_frame('r1')\n"
        "st.session_state['_stages'] = sorted(set(frame['stage']))\n"
        "st.session_state['_rows'] = int(len(frame))\n"
        "st.session_state['_valid'] = r.validate_acbc_responses(frame, al)\n"
    )
    at = _app("st.write('ok')", preamble=preamble).run()
    assert not at.exception
    assert at.session_state["_stages"] == [
        "background",
        "calibration",
        "musthave",
        "rating",
        "tournament",
        "wtp",
    ]
    # 2 background + 25 ratings + 2 constraints + 2 tournament + 2 calibration + 2 wtp.
    assert at.session_state["_rows"] == 35
    assert at.session_state["_valid"] == []
