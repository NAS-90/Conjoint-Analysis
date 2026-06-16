"""End-to-end checks for the linear questionnaire's section hand-offs.

``streamlit``'s ``AppTest`` does not persist ``st.navigation`` page state across
reruns, so rather than walk the multi-page router we exercise the key seams by
seeding session state and driving one section to completion:

* **B1 → B2**: finishing B2 derives the ideal *anchor* from the B1 ratings; and
* a guard that price labels render with ``$`` escaped (never raw LaTeX ``$…$``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from conjoint import questionnaire as q

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = REPO_ROOT / "questionnaire_spec.json"
_NEXT_LABELS = {"Next →", "Finish"}


def _first_level_codes() -> dict[str, str]:
    spec = q.read_spec(DEFAULT_SPEC)
    return {attr.feature_name: attr.levels[0].code for attr in spec.active_attributes}


def _b2_app_with_seeded_ratings() -> AppTest:
    """Render B2 with B1 ratings pre-seeded so the first level scores highest."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import streamlit as st\n"
        "from conjoint import questionnaire as q\n"
        "from survey_views.spec_source import DEFAULT_SPEC\n"
        "from survey_views.state import STAGE_ANSWERS_KEY\n"
        "spec = q.read_spec(DEFAULT_SPEC)\n"
        "st.session_state[STAGE_ANSWERS_KEY] = {'ratings': {\n"
        "    a.feature_name: {lv.code: (5 if i == 0 else 1)\n"
        "                     for i, lv in enumerate(a.levels)}\n"
        "    for a in spec.active_attributes\n"
        "}}\n"
        "from survey_views.b2_constraints import render_constraints\n"
        "render_constraints()\n"
    )
    return AppTest.from_string(script)


@pytest.mark.integration
def test_b2_finish_derives_anchor_from_ratings() -> None:
    """With no constraints set, the anchor is the top-rated level per attribute."""
    from survey_views.state import ACBC_ANCHOR_KEY

    at = _b2_app_with_seeded_ratings().run()
    # B2 pages are always complete (constraints optional) — walk to the Finish.
    for _ in range(20):
        nxt = next((b for b in at.button if b.label in _NEXT_LABELS), None)
        if nxt is None:
            break
        was_finish = nxt.label == "Finish"
        nxt.click().run()
        if was_finish:
            break

    assert not at.exception
    anchor = at.session_state[ACBC_ANCHOR_KEY]
    first_levels = _first_level_codes()
    assert {attr: code for attr, code in anchor.levels} == first_levels


@pytest.mark.integration
def test_b1_price_options_escape_dollar_signs() -> None:
    """B1's price level labels must escape ``$`` (no raw LaTeX ``$…$``)."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.ratings import render_questionnaire\n"
        "render_questionnaire()\n"
    )
    at = AppTest.from_string(script).run()

    # B1 renders one radio per price level; the level label is the radio label.
    price_radios = [
        r for r in at.radio if r.key and r.key.startswith("survey_rating__price__")
    ]
    assert price_radios
    joined = " ".join(r.label for r in price_radios)
    assert "\\$" in joined  # dollars are escaped...
    assert "$" not in joined.replace("\\$", "")  # ...with none left raw
