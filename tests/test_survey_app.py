"""Tests for the standalone survey app (``survey.py`` + :mod:`survey_views`).

Covers:

* the committed ``questionnaire_spec.json`` loads and exposes the active
  attributes the survey renders;
* the Streamlit router runs, defaults to the intro page, and exposes the fixed
  linear page order (no mode gating, no B1 ratings step); and
* a missing spec file surfaces a friendly error instead of crashing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from conjoint import questionnaire as q

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_SPEC = REPO_ROOT / "questionnaire_spec.json"
SURVEY_APP = REPO_ROOT / "survey.py"
DEMO_WORKBOOK = REPO_ROOT / "conjoint_demo.xlsx"

# The committed questionnaire_spec.json (smartphone) → these active B-1
# attributes, in spec order. The survey app renders this *bundled spec*.
EXPECTED_ACTIVE_SPEC = {
    "price": 3,
    "processor": 3,
    "ram": 3,
    "battery": 3,
    "display": 3,
    "camera": 3,
    "storage": 3,
    "card": 2,
    "os": 2,
}
# conjoint_demo.xlsx (tractor) → these active B-1 attributes, in workbook order.
# Exercised only by the workbook-ingestion unit test below.
EXPECTED_ACTIVE_WORKBOOK = {
    "engine": 2,
    "injection": 2,
    "transmission": 4,
    "shuttle": 3,
    "gears": 4,
    "cabin": 3,
    "tank": 3,
}
EXPECTED_RATING_COLUMNS = sum(EXPECTED_ACTIVE_SPEC.values())  # 25


# ---------------------------------------------------------------------------
# Committed spec
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_bundled_spec_exists_and_loads() -> None:
    assert (
        BUNDLED_SPEC.exists()
    ), "questionnaire_spec.json must be committed for the survey"
    spec = q.read_spec(BUNDLED_SPEC)

    active = spec.active_attributes
    assert {attr.feature_name for attr in active} == set(EXPECTED_ACTIVE_SPEC)
    for attr in active:
        assert attr.status == "active"
        assert attr.section == "B1_rating"
        assert len(attr.levels) == EXPECTED_ACTIVE_SPEC[attr.feature_name]
    assert spec.scale == q.Scale(1, 5)
    assert len(q.response_columns(spec)) == EXPECTED_RATING_COLUMNS


# ---------------------------------------------------------------------------
# Router + pages run (AppTest)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_survey_router_runs_default_intro_page() -> None:
    at = AppTest.from_file(str(SURVEY_APP)).run()

    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("survey" in title.lower() for title in titles)


@pytest.mark.unit
def test_ordered_pages_is_linear() -> None:
    """The survey is one fixed linear flow — no mode gating, no B1 ratings."""
    from survey import ordered_pages

    pages = ordered_pages(
        intro="intro",
        part_a="part_a",
        b0="b0",
        b2="b2",
        b4="tournament",
        b5="b5",
        part_c="part_c",
        summary="summary",
    )
    assert pages == [
        "intro",
        "part_a",
        "b0",
        "b2",
        "tournament",
        "b5",
        "part_c",
        "summary",
    ]


@pytest.mark.integration
def test_welcome_has_no_mode_toggle() -> None:
    """The quick-Rating mode was removed — Welcome just starts the one flow."""
    at = AppTest.from_file(str(SURVEY_APP)).run()
    assert not at.exception
    # No mode radio remains; a single "Start" button kicks off the linear flow.
    assert not at.radio
    assert any(b.label.startswith("Start") for b in at.button)


@pytest.mark.integration
def test_missing_spec_file_shows_friendly_error() -> None:
    """When the bundled spec is missing a page surfaces a friendly error.

    Driven through B0 — the first spec-backed page now that B1 is gone. Like
    every section view it calls ``load_spec`` and returns early when the spec
    cannot be read, so the friendly error is shown and the "I'm ready" button
    is never rendered.
    """
    from survey_views import spec_source

    missing = REPO_ROOT / "does_not_exist.json"
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from pathlib import Path\n"
        "from survey_views import spec_source\n"
        f"spec_source.DEFAULT_SPEC = Path({str(missing)!r})\n"
        "from survey_views.b0_features import render_features_intro\n"
        "render_features_intro()\n"
    )
    # The script mutates the shared module global ``DEFAULT_SPEC``; restore it so
    # the bad path can't leak into other AppTests sharing this process.
    original_default_spec = spec_source.DEFAULT_SPEC
    try:
        at = AppTest.from_string(script).run()

        assert not at.exception
        errors = [e.value for e in at.error]
        assert any("administrator" in msg.lower() for msg in errors)
        assert not any(b.label.startswith("I'm ready") for b in at.button)
    finally:
        spec_source.DEFAULT_SPEC = original_default_spec


@pytest.mark.unit
def test_survey_spec_env_var_selects_product(monkeypatch) -> None:
    """``$SURVEY_SPEC`` selects any product's spec without editing the default.

    Switching products is a config change (like ``$SURVEY_WORKBOOK`` for Part
    A/C), not a code edit or an overwrite of the committed default — so the flow
    stays product-agnostic.
    """
    from survey_views import spec_source

    monkeypatch.setenv("SURVEY_SPEC", "/some/product/spec.json")
    assert spec_source._resolve_spec_path() == Path("/some/product/spec.json")

    monkeypatch.delenv("SURVEY_SPEC", raising=False)
    assert spec_source._resolve_spec_path() == spec_source.DEFAULT_SPEC


@pytest.mark.unit
def test_spec_dict_from_workbook_matches_active_attributes() -> None:
    from survey_views.spec_source import _spec_dict_from_workbook

    payload = _spec_dict_from_workbook(DEMO_WORKBOOK.read_bytes(), "conjoint_demo.xlsx")
    names = {attr["feature_name"] for attr in payload["attributes"]}
    assert names == set(EXPECTED_ACTIVE_WORKBOOK)
    assert payload["scale"] == {"min": 1, "max": 5}
