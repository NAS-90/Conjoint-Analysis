"""End-to-end checks for the ACBC survey's stage hand-offs.

The risky seam in the questionnaire is **Screener → Tournament**: the Screener
must publish the accepted configurations as a survivor pool, and the Tournament
must build choice tasks from that (often small) pool without crashing on the
"need 24 profiles" path. ``streamlit``'s ``AppTest`` does not persist
``st.navigation`` page state across reruns, so rather than walk the multi-page
router we verify each side of the hand-off:

* the Screener, run to completion, populates ``ACBC_SURVIVORS_KEY``;
* (paired with ``test_acbc_tournament_view`` which feeds a small survivor pool
  into the Tournament and reaches the Thank-you confirmation).

Plus a guard that the Welcome → Step-1 navigation renders price labels with
``$`` escaped (never raw LaTeX ``$…$``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent
SURVEY_APP = REPO_ROOT / "survey.py"

MODE_ACBC = "Build and compare (about 10 minutes)"
_NEXT_LABELS = {"Next →", "Finish"}


def _button(at: AppTest, labels: set[str]):
    return next((b for b in at.button if b.label in labels), None)


def _screener_app() -> AppTest:
    """An ``AppTest`` running the Screener standalone with a seeded anchor."""
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
        "    (a.feature_name, a.levels[0].code) for a in spec.active_attributes\n"
        "))\n"
        "st.session_state[ACBC_ANCHOR_KEY] = anchor\n"
        "from survey_views.acbc_screener import render_screener\n"
        "render_screener()\n"
    )
    return AppTest.from_string(script)


@pytest.mark.integration
def test_screener_completion_populates_survivor_pool() -> None:
    """Answering the whole Screener publishes the survivors the Tournament reads."""
    from survey_views.acbc_byo import ACBC_ANCHOR_KEY
    from survey_views.acbc_screener import ACBC_SURVIVORS_KEY

    at = _screener_app().run()
    for _ in range(40):  # more than the screener pool size, breaks when done
        radio = next(
            (r for r in at.radio if r.key and r.key.startswith("acbc_screener__profile__")),
            None,
        )
        if radio is None:
            break
        radio.set_value("Yes").run()
        nxt = _button(at, _NEXT_LABELS)
        if nxt is None:
            break
        nxt.click().run()

    assert not at.exception
    survivors = at.session_state[ACBC_SURVIVORS_KEY]
    # Every profile accepted → survivors carry the accepted pool + the anchor.
    assert len(survivors) >= 2
    assert at.session_state[ACBC_ANCHOR_KEY] in survivors


@pytest.mark.integration
def test_byo_price_options_escape_dollar_signs() -> None:
    """The price question's labels must escape ``$`` (no raw LaTeX ``$…$``)."""
    at = AppTest.from_file(str(SURVEY_APP)).run()
    at.radio[0].set_value(MODE_ACBC).run()
    _button(at, {"Start →"}).click().run()

    # First BYO question is Price; its options render via a safe_md format_func.
    price = next(r for r in at.radio if r.key == "acbc_byo__price")
    rendered = [price.format_func(opt) for opt in price.options]
    joined = " ".join(rendered)
    assert "\\$" in joined  # dollars are escaped...
    assert "$" not in joined.replace("\\$", "")  # ...with none left raw
