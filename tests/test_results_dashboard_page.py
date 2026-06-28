"""Smoke tests for :mod:`dashboard.results_dashboard`.

Following the project convention (``test_quality_diagnostics_page.py`` tests the
pure core, not the live Streamlit runtime) we exercise the ``_render_*`` section
functions with a recording ``FakeSt`` stub and a small real
:class:`~dashboard.results_analysis.SurveyResults`, asserting each section runs
end-to-end and emits output.
"""

from __future__ import annotations

import pytest

from conjoint import questionnaire as q
from conjoint.acbc import respondent_sim as rs
from conjoint.acbc.design import attribute_levels_from_spec
from dashboard import results_dashboard as rd
from dashboard.results_analysis import analyze_survey_results
from survey_views import section_source as ss

SPEC_PATH = "questionnaire_spec_computers.json"
WORKBOOK = "computer_survey_questions.xlsx"


class FakeSt:
    """A minimal recording Streamlit stand-in (inputs return defaults)."""

    def __init__(self, sink: dict | None = None) -> None:
        self.sink = sink if sink is not None else {"plotly_chart": 0, "dataframe": 0, "metric": 0, "info": 0}
        self.sidebar = self

    # context-manager (for columns / expander / container)
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    # layout
    def columns(self, spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [FakeSt(self.sink) for _ in range(n)]

    def expander(self, *args, **kwargs):
        return FakeSt(self.sink)

    def container(self, *args, **kwargs):
        return FakeSt(self.sink)

    # inputs → deterministic defaults
    def selectbox(self, label, options, index=0, **kwargs):
        options = list(options)
        return options[index or 0] if options else None

    def radio(self, label, options, index=0, **kwargs):
        options = list(options)
        return options[index or 0] if options else None

    def multiselect(self, label, options, default=None, **kwargs):
        return list(default) if default else []

    def number_input(self, label, value=0, **kwargs):
        return value

    def slider(self, label, min_value=None, max_value=None, value=None, **kwargs):
        return value

    def select_slider(self, label, options=None, value=None, **kwargs):
        return value

    def text_input(self, label, value="", **kwargs):
        return value

    def file_uploader(self, *args, **kwargs):
        return None

    # outputs → record
    def plotly_chart(self, *args, **kwargs):
        self.sink["plotly_chart"] += 1

    def dataframe(self, *args, **kwargs):
        self.sink["dataframe"] += 1

    def table(self, *args, **kwargs):
        self.sink["dataframe"] += 1

    def metric(self, *args, **kwargs):
        self.sink["metric"] += 1

    def info(self, *args, **kwargs):
        self.sink["info"] += 1

    # no-op for markdown / caption / subheader / write / success / warning / error / ...
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


@pytest.fixture(scope="module", autouse=True)
def _survey_env():
    import os

    previous = {key: os.environ.get(key) for key in ("SURVEY_SPEC", "SURVEY_WORKBOOK")}
    os.environ["SURVEY_SPEC"] = SPEC_PATH
    os.environ["SURVEY_WORKBOOK"] = WORKBOOK
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def ctx():
    return rd.load_context()


@pytest.fixture(scope="module")
def results():
    spec = q.read_spec(SPEC_PATH)
    questions = ss.load_background_questions(WORKBOOK)
    features = ss.load_wtp_features(WORKBOOK)
    bands = ss.load_amount_bands(WORKBOOK)
    fa = rs.default_wtp_feature_attribute(features, attribute_levels_from_spec(spec))
    frame, _, _ = rs.generate_synthetic_responses(
        spec, questions=questions, wtp_features=features, amount_bands=bands,
        wtp_feature_attribute=fa, n_respondents=15, seed=1,
    )
    price_labels = {
        level.code: level.label
        for attr in spec.attributes
        if attr.feature_name == "price"
        for level in attr.levels
    }
    return analyze_survey_results(frame, amount_bands=bands, price_labels=price_labels, hb_iter=120, seed=0)


@pytest.mark.integration
def test_load_context_is_populated(ctx) -> None:
    assert "price" in ctx.attribute_levels
    assert len(ctx.bands) >= 2
    assert len(ctx.features) >= 1
    assert ctx.labels["price"]  # level labels present


@pytest.mark.unit
def test_display_helpers() -> None:
    assert rd.attr_name("ram") == "RAM"
    assert rd.attr_name("touchscreen") == "Touchscreen"


@pytest.mark.integration
def test_all_sections_render(results, ctx) -> None:
    sink = {"plotly_chart": 0, "dataframe": 0, "metric": 0, "info": 0}
    st = FakeSt(sink)

    rd._render_overview(st, results)
    rd._render_importance(st, results, ctx)
    rd._render_partworths(st, results, ctx)
    rd._render_wtp(st, results, ctx)
    rd._render_simulator(st, results, ctx)
    rd._render_calibration(st, results)
    rd._render_segments(st, results, ctx)

    # every section drew at least one chart; overview emitted metrics
    assert sink["plotly_chart"] >= 6
    assert sink["metric"] >= 3


@pytest.mark.integration
def test_results_workbook_bundles_every_section(results, ctx) -> None:
    import io

    import pandas as pd

    from dashboard.exporting import workbook_bytes

    sheets = rd._results_workbook_sheets(results, ctx)
    # core outputs are always present; synthetic data also has WTP/B5/Part A
    for expected in (
        "Importance",
        "Part-worth utilities",
        "WTP (stated)",
        "Purchase intent",
        "Segments",
        "HB utilities",
    ):
        assert expected in sheets, f"missing {expected!r} sheet"

    # the whole bundle serialises to one readable workbook
    back = pd.read_excel(io.BytesIO(workbook_bytes(sheets)), sheet_name=None, engine="openpyxl")
    assert set(back) == set(sheets)


@pytest.mark.integration
def test_simulator_default_products_are_differentiated(ctx) -> None:
    first = rd._default_product_spec(ctx, 0)
    second = rd._default_product_spec(ctx, 1)
    assert first != second  # different default levels per product


@pytest.mark.unit
def test_product_label() -> None:
    assert rd._product_label("survey_responses_computers") == "Computers"
    assert rd._product_label("survey_responses_smart_phones") == "Smart Phones"


@pytest.mark.unit
def test_pick_responses_dir_defaults_to_active_product(monkeypatch) -> None:
    discovered = [
        ("Computers", "outputs/survey_responses_computers"),
        ("Smartphones", "outputs/survey_responses_smartphones"),
    ]
    monkeypatch.setattr(rd, "_discover_response_dirs", lambda: discovered)
    monkeypatch.setattr(
        rd, "_default_responses_dir", lambda: "outputs/survey_responses_smartphones"
    )
    # The dropdown pre-selects the folder matching the active product spec.
    assert rd._pick_responses_dir(FakeSt()) == "outputs/survey_responses_smartphones"


@pytest.mark.unit
def test_pick_responses_dir_falls_back_to_text_input(monkeypatch) -> None:
    monkeypatch.setattr(rd, "_discover_response_dirs", lambda: [])
    monkeypatch.setattr(rd, "_default_responses_dir", lambda: "outputs/survey_responses_x")
    # No folders discovered → plain text input pre-filled with the default path.
    assert rd._pick_responses_dir(FakeSt()) == "outputs/survey_responses_x"


# ---------------------------------------------------------------------------
# Product → context resolution: selecting a product folder must switch the
# spec/labels/bands, not just the responses. (Regression: the dropdown used to
# change the data while the page stayed frozen on the launch product's spec.)
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_product_from_dir() -> None:
    assert rd._product_from_dir("outputs/survey_responses_computers") == "computers"
    assert rd._product_from_dir("outputs/survey_responses_smartphones") == "smartphones"
    # free-form path / upload → no product token (keep launch-time context)
    assert rd._product_from_dir("some/other/folder") is None
    assert rd._product_from_dir(None) is None
    assert rd._product_from_dir("") is None


@pytest.mark.unit
def test_spec_for_product_resolves_per_product() -> None:
    assert rd._spec_for_product("computers").name == "questionnaire_spec_computers.json"
    assert rd._spec_for_product("smartphones").name == "questionnaire_spec_smartphones.json"
    # unknown product → env/default spec rather than a missing file
    assert rd._spec_for_product("teleporter") == rd._spec_path()
    assert rd._spec_for_product(None) == rd._spec_path()


@pytest.mark.unit
def test_workbook_for_product_resolves_per_product() -> None:
    # singular spelling on disk for computers; bare default for smartphones
    assert rd._workbook_for_product("computers").name == "computer_survey_questions.xlsx"
    assert rd._workbook_for_product("smartphones").name == "survey_questions.xlsx"
    # no product (uploads) → defer to load_context's env/default logic
    assert rd._workbook_for_product(None) is None


@pytest.mark.unit
def test_resolve_context_paths_follows_folder() -> None:
    spec_key, workbook_key = rd._resolve_context_paths("outputs/survey_responses_computers")
    assert spec_key.endswith("questionnaire_spec_computers.json")
    assert workbook_key.endswith("computer_survey_questions.xlsx")

    spec_key, workbook_key = rd._resolve_context_paths("outputs/survey_responses_smartphones")
    assert spec_key.endswith("questionnaire_spec_smartphones.json")
    assert workbook_key.endswith("survey_questions.xlsx")


@pytest.mark.integration
def test_context_follows_selected_product() -> None:
    """The whole point of the fix: context attributes/labels switch with the product."""
    phones = rd.load_context(
        rd._spec_for_product("smartphones"), rd._workbook_for_product("smartphones")
    )
    computers = rd.load_context(
        rd._spec_for_product("computers"), rd._workbook_for_product("computers")
    )

    # Each product exposes its own attributes in the simulator/labels.
    assert {"camera", "card"} <= set(phones.attribute_levels)
    assert {"graphics", "touchscreen"} <= set(computers.attribute_levels)
    assert "touchscreen" not in phones.attribute_levels
    assert "camera" not in computers.attribute_levels

    # Price tier labels are product-specific (phones < $300 vs computers < $600).
    assert phones.labels["price"]["budget"] != computers.labels["price"]["budget"]
