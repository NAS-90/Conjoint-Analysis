"""Unit tests for :mod:`dashboard.exporting`.

These exercise the pure helpers with a tiny recording stub (the same pattern as
``test_results_dashboard_page.py``'s ``FakeSt``) so no Streamlit runtime or
image backend is needed.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from dashboard.exporting import (
    DEFAULT_IMAGE_SCALE,
    chart_config,
    download_csv_button,
    download_workbook_button,
    render_chart,
    workbook_bytes,
)


class RecordingSt:
    """Records the args of the two output calls the helpers make."""

    def __init__(self) -> None:
        self.plotly_calls: list[dict] = []
        self.download_calls: list[dict] = []

    def plotly_chart(self, fig, **kwargs) -> None:
        self.plotly_calls.append({"fig": fig, **kwargs})

    def download_button(self, label, **kwargs) -> None:
        self.download_calls.append({"label": label, **kwargs})


@pytest.mark.unit
def test_chart_config_sets_png_export_options() -> None:
    config = chart_config("Attribute Importance!", scale=2)
    opts = config["toImageButtonOptions"]
    assert opts["format"] == "png"
    assert opts["filename"] == "Attribute_Importance"  # slugified, no extension
    assert opts["scale"] == 2
    assert config["displayModeBar"] is True
    assert config["displaylogo"] is False


@pytest.mark.unit
def test_chart_config_default_scale_and_empty_name() -> None:
    config = chart_config("   ")
    assert config["toImageButtonOptions"]["scale"] == DEFAULT_IMAGE_SCALE
    assert config["toImageButtonOptions"]["filename"] == "chart"  # fallback stem


@pytest.mark.unit
def test_render_chart_passes_config_and_width() -> None:
    st = RecordingSt()
    sentinel = object()
    render_chart(st, sentinel, filename="my_chart")
    assert len(st.plotly_calls) == 1
    call = st.plotly_calls[0]
    assert call["fig"] is sentinel
    assert call["use_container_width"] is True
    assert call["config"]["toImageButtonOptions"]["filename"] == "my_chart"


@pytest.mark.unit
def test_download_csv_button_encodes_utf8_and_preserves_frame() -> None:
    st = RecordingSt()
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    before = df.copy(deep=True)

    download_csv_button(st, df, label="Download", file_name="data.csv", key="k")

    call = st.download_calls[0]
    assert call["label"] == "Download"
    assert call["file_name"] == "data.csv"
    assert call["mime"] == "text/csv"
    assert call["key"] == "k"
    assert call["data"] == df.to_csv(index=False).encode("utf-8")
    # the helper must never mutate the caller's frame
    pd.testing.assert_frame_equal(df, before)


@pytest.mark.unit
def test_download_csv_button_rejects_non_dataframe() -> None:
    st = RecordingSt()
    with pytest.raises(TypeError):
        download_csv_button(st, {"not": "a frame"}, label="x", file_name="x.csv")


@pytest.mark.unit
def test_workbook_bytes_roundtrips_every_sheet() -> None:
    sheets = {
        "Importance": pd.DataFrame({"Attribute": ["RAM"], "value": [0.4]}),
        "HB utilities": pd.DataFrame({"respondent": [1, 2], "u": [0.1, 0.2]}),
    }
    data = workbook_bytes(sheets)
    back = pd.read_excel(io.BytesIO(data), sheet_name=None, engine="openpyxl")
    assert set(back) == {"Importance", "HB utilities"}
    pd.testing.assert_frame_equal(back["HB utilities"], sheets["HB utilities"])


@pytest.mark.unit
def test_workbook_bytes_sanitizes_and_truncates_sheet_titles() -> None:
    long_invalid = "Willingness:to/pay [stated] " + "x" * 40
    data = workbook_bytes({long_invalid: pd.DataFrame({"a": [1]})})
    [title] = list(pd.read_excel(io.BytesIO(data), sheet_name=None, engine="openpyxl"))
    assert len(title) <= 31
    assert not set(title) & set("[]:*?/\\")


@pytest.mark.unit
def test_workbook_bytes_rejects_empty_mapping() -> None:
    with pytest.raises(ValueError):
        workbook_bytes({})


@pytest.mark.unit
def test_download_workbook_button_drops_empty_frames() -> None:
    st = RecordingSt()
    download_workbook_button(
        st,
        {"Has rows": pd.DataFrame({"a": [1]}), "Empty": pd.DataFrame()},
        label="Download all results",
        file_name="results.xlsx",
        key="dl_all",
    )
    assert len(st.download_calls) == 1
    call = st.download_calls[0]
    assert call["file_name"] == "results.xlsx"
    assert "spreadsheetml" in call["mime"]
    # the empty sheet was dropped, so the workbook holds only the non-empty one
    back = pd.read_excel(io.BytesIO(call["data"]), sheet_name=None, engine="openpyxl")
    assert list(back) == ["Has rows"]


@pytest.mark.unit
def test_download_workbook_button_skips_when_all_empty() -> None:
    st = RecordingSt()
    download_workbook_button(
        st,
        {"Empty": pd.DataFrame()},
        label="Download",
        file_name="results.xlsx",
    )
    assert st.download_calls == []
