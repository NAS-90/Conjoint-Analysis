"""Shared Streamlit export helpers: hi-res chart PNGs + dataset CSV downloads.

The Conjoint Results dashboard (:mod:`dashboard.results_dashboard`) renders
Plotly charts and tabular analysis outputs. These helpers let a client take both
away without any server-side image backend:

* **Save any chart as an image** — :func:`render_chart` wraps
  ``st.plotly_chart`` with a modebar configured for a high-resolution PNG export
  (the 📷 icon). The export happens client-side in the browser, so no
  ``kaleido`` dependency is required.
* **Download any dataset** — :func:`download_csv_button` wraps
  ``st.download_button`` with a UTF-8 CSV payload built from a DataFrame.

Both take an explicit ``st`` handle (the module, a column, or the sidebar) so
they stay unit-testable with the dashboard's ``FakeSt`` stub, matching the
existing ``_render_*`` convention.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

#: Default PNG upscaling factor for chart exports (3× ≈ presentation quality).
DEFAULT_IMAGE_SCALE = 3

#: Modebar buttons that add noise without helping a business reader.
_REMOVED_MODEBAR_BUTTONS = ("lasso2d", "select2d")


def _safe_filename(name: str) -> str:
    """Slugify ``name`` into a download-safe stem (no extension)."""
    stem = re.sub(r"[^0-9A-Za-z_-]+", "_", str(name).strip()).strip("_")
    return stem or "chart"


def chart_config(filename: str, *, scale: int = DEFAULT_IMAGE_SCALE) -> dict[str, Any]:
    """Plotly ``config`` enabling a hi-res PNG export from the modebar 📷.

    The exported file is ``<filename>.png`` at ``scale``× the on-screen
    resolution. The modebar is pinned visible so the export control is
    discoverable rather than hover-only.
    """
    return {
        "displaylogo": False,
        "displayModeBar": True,
        "modeBarButtonsToRemove": list(_REMOVED_MODEBAR_BUTTONS),
        "toImageButtonOptions": {
            "format": "png",
            "filename": _safe_filename(filename),
            "scale": scale,
        },
    }


def render_chart(
    st: Any,
    fig: Any,
    *,
    filename: str,
    scale: int = DEFAULT_IMAGE_SCALE,
    use_container_width: bool = True,
    **kwargs: Any,
) -> None:
    """Render a Plotly ``fig`` with a PNG-export-ready modebar.

    Drop-in for ``st.plotly_chart(fig, use_container_width=True)``; the only
    required extra is ``filename`` (the PNG download stem). ``st`` may be the
    Streamlit module, a column, or the sidebar.
    """
    st.plotly_chart(
        fig,
        use_container_width=use_container_width,
        config=chart_config(filename, scale=scale),
        **kwargs,
    )


def download_csv_button(
    st: Any,
    df: pd.DataFrame,
    *,
    label: str,
    file_name: str,
    key: str | None = None,
) -> None:
    """Offer ``df`` as a downloadable UTF-8 CSV via ``st.download_button``.

    The frame is never mutated: ``to_csv`` returns a fresh string which we
    encode to bytes. ``file_name`` should include the ``.csv`` suffix.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"download_csv_button expects a DataFrame, got {type(df)!r}")
    st.download_button(
        label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        key=key,
    )
