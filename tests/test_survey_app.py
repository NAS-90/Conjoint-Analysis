"""Tests for the standalone survey app (``survey.py`` + :mod:`survey_views`).

Covers two contracts:

* the committed ``questionnaire_spec.json`` loads and exposes the active Part
  B-1 attributes the survey renders; and
* the Streamlit router + ratings page actually run (via ``AppTest``), rendering
  one rating widget per (attribute, level) and a submit button — without raising.
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

# conjoint_demo.xlsx → these active B-1 attributes, in workbook order.
EXPECTED_ACTIVE = {
    "engine": 2,
    "injection": 2,
    "transmission": 4,
    "shuttle": 3,
    "gears": 4,
    "cabin": 3,
    "tank": 3,
}
EXPECTED_RATING_COLUMNS = sum(EXPECTED_ACTIVE.values())  # 21


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
    assert {attr.feature_name for attr in active} == set(EXPECTED_ACTIVE)
    for attr in active:
        assert attr.status == "active"
        assert attr.section == "B1_rating"
        assert len(attr.levels) == EXPECTED_ACTIVE[attr.feature_name]
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
    assert "Conjoint desirability survey" in titles


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


@pytest.mark.integration
def test_ratings_page_renders_one_widget_per_level() -> None:
    at = _ratings_app().run()

    assert not at.exception
    rating_radios = _rating_radios(at)
    assert len(rating_radios) == EXPECTED_RATING_COLUMNS
    # Ratings start unselected so progress is meaningful.
    assert all(r.value is None for r in rating_radios)
    assert any(b.label == "Build responses.csv" for b in at.button)


@pytest.mark.integration
def test_custom_attribute_flow_renders_only_user_choices() -> None:
    at = _ratings_app().run()
    _questionnaire_flow(at).set_value("Choose attributes").run()

    attr_selector = next(
        m for m in at.multiselect if m.label == "Attributes to include"
    )
    attr_selector.set_value(["engine", "cabin"]).run()

    assert not at.exception
    rating_radios = _rating_radios(at)
    assert len(rating_radios) == EXPECTED_ACTIVE["engine"] + EXPECTED_ACTIVE["cabin"]
    assert all(
        radio.key.startswith("survey_rating__engine__")
        or radio.key.startswith("survey_rating__cabin__")
        for radio in rating_radios
    )
    assert any("attribute(s) are skipped" in msg.value for msg in at.info)


@pytest.mark.integration
def test_submitting_complete_ratings_yields_valid_responses() -> None:
    at = _ratings_app().run()

    for radio in _rating_radios(at):
        radio.set_value(3)  # any in-scale value
    at.run()

    submit = next(b for b in at.button if b.label == "Build responses.csv")
    submit.click().run()

    assert not at.exception
    # Validation passed → success message + the responses frame is shown.
    assert any("look valid" in msg.value for msg in at.success)
    assert len(at.dataframe) == 1


@pytest.mark.integration
def test_submitting_blank_survey_warns_but_still_validates() -> None:
    # A partially-completed survey is allowed: blanks stay empty, no error.
    at = _ratings_app().run()
    submit = next(b for b in at.button if b.label == "Build responses.csv")
    submit.click().run()

    assert not at.exception
    assert any("not fully rated" in w.value for w in at.warning)
    assert any("look valid" in msg.value for msg in at.success)


@pytest.mark.integration
def test_missing_spec_path_warns_and_renders_no_widgets() -> None:
    at = _ratings_app().run()
    spec_path = next(t for t in at.text_input if t.label == "Spec path")
    spec_path.set_value(str(REPO_ROOT / "does_not_exist.json")).run()

    assert not at.exception
    assert any("No spec found" in w.value for w in at.warning)
    assert _rating_radios(at) == []


@pytest.mark.unit
def test_spec_dict_from_workbook_matches_active_attributes() -> None:
    from survey_views.spec_source import _spec_dict_from_workbook

    payload = _spec_dict_from_workbook(DEMO_WORKBOOK.read_bytes(), "conjoint_demo.xlsx")
    names = {attr["feature_name"] for attr in payload["attributes"]}
    assert names == set(EXPECTED_ACTIVE)
    assert payload["scale"] == {"min": 1, "max": 5}
