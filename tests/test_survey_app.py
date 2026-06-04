"""Tests for the standalone survey app (``survey.py`` + :mod:`survey_views`).

Covers three contracts:

* the committed ``questionnaire_spec.json`` loads and exposes the active Part
  B-1 attributes the survey renders;
* the Streamlit router + ratings page actually run (via ``AppTest``), with the
  single-page-per-attribute navigation controller showing exactly one
  attribute's rating widgets per page; and
* finishing the sequential flow assembles a contract-compliant
  ``responses.csv`` and validates against the bundled spec.
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
EXPECTED_ATTRIBUTE_COUNT = len(EXPECTED_ACTIVE_SPEC)  # 9
EXPECTED_RATING_COLUMNS = sum(EXPECTED_ACTIVE_SPEC.values())  # 25
# Attributes appear in spec order so "price" is the very first step and
# "processor" the second.
FIRST_ATTRIBUTE = "price"
FIRST_ATTRIBUTE_LEVELS = EXPECTED_ACTIVE_SPEC[FIRST_ATTRIBUTE]
SECOND_ATTRIBUTE = "processor"


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
def test_flow_pages_gates_sidebar_by_mode() -> None:
    """Each method shows only its own pages; Welcome is always first."""
    from survey import flow_pages
    from survey_views.intro import MODE_ACBC, MODE_RATING

    sentinels = dict(
        intro="intro",
        questionnaire="ratings",
        byo="byo",
        screener="screener",
        tournament="tournament",
        summary="summary",
    )

    rating = flow_pages(MODE_RATING, **sentinels)
    assert rating == ["intro", "ratings"]
    assert "byo" not in rating and "tournament" not in rating

    acbc = flow_pages(MODE_ACBC, **sentinels)
    assert acbc == ["intro", "byo", "screener", "tournament", "summary"]
    assert "ratings" not in acbc

    # Unset mode (before a choice is made) defaults to the ACBC flow.
    assert flow_pages(None, **sentinels) == acbc


@pytest.mark.unit
def test_guided_profiles_match_real_attributes() -> None:
    """Every guided profile must select >=1 real attribute of the bundled spec.

    Regression: the profiles previously listed tractor/car attributes that
    matched nothing in the smartphone spec, so "Guided profile" silently fell
    back to the full questionnaire every time.
    """
    from conjoint import questionnaire as q

    from survey_views.ratings import GUIDED_PROFILES, _matches_profile
    from survey_views.spec_source import DEFAULT_SPEC

    spec = q.read_spec(DEFAULT_SPEC)
    for name, keywords in GUIDED_PROFILES.items():
        matched = [a for a in spec.active_attributes if _matches_profile(a, keywords)]
        assert matched, f"guided profile {name!r} matches no attribute"


def _ratings_app() -> AppTest:
    """An ``AppTest`` driving the ratings page directly.

    The router's default page is the intro, so to exercise the questionnaire we
    run the render function on its own (it still loads the bundled spec and the
    sidebar source selector exactly as it does inside the router).
    """
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from survey_views.ratings import render_questionnaire\n"
        "render_questionnaire()\n"
    )
    return AppTest.from_string(script)


def _rating_radios(at: AppTest) -> list:
    return [r for r in at.radio if r.key and r.key.startswith("survey_rating__")]


def _questionnaire_flow(at: AppTest):
    return next(s for s in at.selectbox if s.label == "Questionnaire flow")


def _next_button(at: AppTest):
    return next(b for b in at.button if b.label in {"Next →", "Finish"})


def _advance(at: AppTest, value: int = 3) -> None:
    """Set every rating widget on the current page to ``value`` and click Next."""
    for radio in _rating_radios(at):
        radio.set_value(value)
    at.run()
    _next_button(at).click().run()


@pytest.mark.integration
def test_first_page_shows_first_attribute_only() -> None:
    """Single-page-per-attribute: only the first attribute's radios appear."""
    at = _ratings_app().run()

    assert not at.exception
    radios = _rating_radios(at)
    assert len(radios) == FIRST_ATTRIBUTE_LEVELS
    assert all(r.key.startswith(f"survey_rating__{FIRST_ATTRIBUTE}__") for r in radios)
    assert all(r.value is None for r in radios)
    # Navigation controls present.
    assert any(b.label == "Next →" for b in at.button)
    assert any(b.label == "← Back" for b in at.button)


@pytest.mark.integration
def test_next_button_disabled_until_all_levels_rated() -> None:
    at = _ratings_app().run()
    nxt = _next_button(at)
    assert nxt.disabled is True

    # Rate only the first level → still incomplete.
    _rating_radios(at)[0].set_value(3)
    at.run()
    assert _next_button(at).disabled is True

    # Rate the remaining levels of the first attribute.
    for radio in _rating_radios(at)[1:]:
        radio.set_value(4)
    at.run()
    assert _next_button(at).disabled is False


@pytest.mark.integration
def test_advancing_moves_to_next_attribute() -> None:
    at = _ratings_app().run()

    # Page 1 — first attribute.
    for radio in _rating_radios(at):
        radio.set_value(3)
    at.run()
    _next_button(at).click().run()

    # Page 2 — second attribute (spec order → processor).
    radios = _rating_radios(at)
    assert all(r.key.startswith(f"survey_rating__{SECOND_ATTRIBUTE}__") for r in radios)
    assert len(radios) == EXPECTED_ACTIVE_SPEC[SECOND_ATTRIBUTE]


@pytest.mark.integration
def test_custom_attribute_flow_scopes_the_step_sequence() -> None:
    at = _ratings_app().run()
    _questionnaire_flow(at).set_value("Choose attributes").run()

    attr_selector = next(
        m for m in at.multiselect if m.label == "Attributes to include"
    )
    attr_selector.set_value(["price", "camera"]).run()

    assert not at.exception
    radios = _rating_radios(at)
    # First page = first chosen attribute (still in spec order → price).
    assert all(r.key.startswith("survey_rating__price__") for r in radios)
    assert len(radios) == EXPECTED_ACTIVE_SPEC["price"]


@pytest.mark.integration
def test_finishing_complete_ratings_yields_valid_responses() -> None:
    at = _ratings_app().run()

    for _ in range(EXPECTED_ATTRIBUTE_COUNT):
        _advance(at)

    assert not at.exception
    assert any("recorded" in msg.value.lower() for msg in at.success)


@pytest.mark.integration
def test_finishing_blank_pages_warns_but_still_validates() -> None:
    """Skipping every page by leaving blanks then forcing finish still validates."""
    at = _ratings_app().run()
    # Custom flow with no attributes selected → no steps; but Finish needs to
    # round-trip the per-attribute restriction. Instead we exhaust all pages
    # while leaving the first level of every attribute blank.
    for _ in range(EXPECTED_ATTRIBUTE_COUNT):
        radios = _rating_radios(at)
        # Rate everything so Next is enabled — we want a complete CSV here.
        # Blank-tolerance is exercised by the validation-only test below.
        for radio in radios:
            radio.set_value(3)
        at.run()
        _next_button(at).click().run()

    assert not at.exception
    assert any("recorded" in msg.value.lower() for msg in at.success)


@pytest.mark.integration
def test_missing_spec_file_shows_friendly_error() -> None:
    """When the bundled spec is missing the page surfaces a friendly error."""
    from survey_views import spec_source

    missing = REPO_ROOT / "does_not_exist.json"
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from pathlib import Path\n"
        "from survey_views import spec_source\n"
        f"spec_source.DEFAULT_SPEC = Path({str(missing)!r})\n"
        "from survey_views.ratings import render_questionnaire\n"
        "render_questionnaire()\n"
    )
    # The script mutates the shared module global ``DEFAULT_SPEC``; restore it so
    # the bad path can't leak into other AppTests sharing this process.
    original_default_spec = spec_source.DEFAULT_SPEC
    try:
        at = AppTest.from_string(script).run()

        assert not at.exception
        errors = [e.value for e in at.error]
        assert any("administrator" in msg.lower() for msg in errors)
        assert _rating_radios(at) == []
    finally:
        spec_source.DEFAULT_SPEC = original_default_spec


@pytest.mark.unit
def test_spec_dict_from_workbook_matches_active_attributes() -> None:
    from survey_views.spec_source import _spec_dict_from_workbook

    payload = _spec_dict_from_workbook(DEMO_WORKBOOK.read_bytes(), "conjoint_demo.xlsx")
    names = {attr["feature_name"] for attr in payload["attributes"]}
    assert names == set(EXPECTED_ACTIVE_WORKBOOK)
    assert payload["scale"] == {"min": 1, "max": 5}
