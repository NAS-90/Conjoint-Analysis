"""End-to-end checks for the linear questionnaire's section hand-offs.

``streamlit``'s ``AppTest`` does not persist ``st.navigation`` page state across
reruns, so rather than walk the multi-page router we exercise the key seams by
seeding session state and driving one section to completion:

* **B2 anchor**: finishing B2 derives the ideal *anchor* from the spec's level
  order (the B1 rating step was removed), honouring any B2 constraints; and
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


def _b2_app() -> AppTest:
    """Render B2 stand-alone (there is no ratings stage — B1 was removed)."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.b2_constraints import render_constraints\n"
        "render_constraints()\n"
    )
    return AppTest.from_string(script)


@pytest.mark.integration
def test_b2_finish_derives_anchor_from_spec_order() -> None:
    """With no constraints set, the anchor is the first level per attribute.

    Without B1 ratings to rank levels, ``anchor_from_ratings`` falls back to the
    spec's level order, so the derived ideal is each attribute's first level.
    """
    from survey_views.state import ACBC_ANCHOR_KEY

    at = _b2_app().run()
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
def test_price_options_escape_dollar_signs() -> None:
    """Price level labels must escape ``$`` (no raw LaTeX ``$…$``).

    Checked on B0 — the first page that lists every level now that B1 is gone.
    """
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.b0_features import render_features_intro\n"
        "render_features_intro()\n"
    )
    at = AppTest.from_string(script).run()
    assert not at.exception

    # B0 lists every level (price included) as Markdown bullets via ``format_level``.
    joined = " ".join(m.value for m in at.markdown)
    assert "\\$" in joined  # dollars are escaped...
    assert "$" not in joined.replace("\\$", "")  # ...with none left raw
