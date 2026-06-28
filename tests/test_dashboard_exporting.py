"""Unit tests for :mod:`dashboard.exporting`.

These exercise the pure helpers with a tiny recording stub (the same pattern as
``test_results_dashboard_page.py``'s ``FakeSt``) so no Streamlit runtime or
image backend is needed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard.exporting import (
    DEFAULT_IMAGE_SCALE,
    chart_config,
    download_csv_button,
    render_chart,
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
