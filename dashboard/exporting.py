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

import io
import re
from collections.abc import Mapping
from typing import Any

import pandas as pd

#: Default PNG upscaling factor for chart exports (3× ≈ presentation quality).
DEFAULT_IMAGE_SCALE = 3

#: Modebar buttons that add noise without helping a business reader.
_REMOVED_MODEBAR_BUTTONS = ("lasso2d", "select2d")

#: MIME type for a modern ``.xlsx`` workbook.
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Characters Excel forbids in a worksheet name.
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


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


def _safe_sheet_name(name: str) -> str:
    """Coerce ``name`` into a valid Excel worksheet title (≤ 31 chars)."""
    cleaned = _INVALID_SHEET_CHARS.sub(" ", str(name)).strip()
    return (cleaned or "Sheet")[:31]


def _unique_sheet_name(name: str, used: set[str]) -> str:
    """Disambiguate ``name`` against already-used titles, staying ≤ 31 chars."""
    if name not in used:
        return name
    for suffix in range(2, 100):
        tag = f" ({suffix})"
        candidate = f"{name[: 31 - len(tag)]}{tag}"
        if candidate not in used:
            return candidate
    return name[:31]


def workbook_bytes(sheets: Mapping[str, pd.DataFrame]) -> bytes:
    """Serialise ``{sheet_name: DataFrame}`` into one in-memory ``.xlsx``.

    One worksheet per entry, in iteration order. Sheet titles are sanitised
    for Excel's constraints (≤ 31 chars, no ``[]:*?/\\``) and de-duplicated.
    """
    if not sheets:
        raise ValueError("workbook_bytes needs at least one sheet")
    buffer = io.BytesIO()
    used: set[str] = set()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"sheet {name!r} must be a DataFrame, got {type(frame)!r}")
            title = _unique_sheet_name(_safe_sheet_name(name), used)
            used.add(title)
            frame.to_excel(writer, sheet_name=title, index=False)
    return buffer.getvalue()


def download_workbook_button(
    st: Any,
    sheets: Mapping[str, pd.DataFrame],
    *,
    label: str,
    file_name: str,
    key: str | None = None,
) -> None:
    """Offer several DataFrames as one downloadable multi-sheet ``.xlsx``.

    Empty frames are dropped; if nothing remains, no button is rendered.
    ``file_name`` should include the ``.xlsx`` suffix.
    """
    present = {
        name: frame
        for name, frame in sheets.items()
        if isinstance(frame, pd.DataFrame) and not frame.empty
    }
    if not present:
        return
    st.download_button(
        label,
        data=workbook_bytes(present),
        file_name=file_name,
        mime=_XLSX_MIME,
        key=key,
    )
