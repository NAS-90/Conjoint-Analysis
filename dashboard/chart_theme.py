"""Shared visual theme for the Conjoint Results charts.

The results dashboard (:mod:`dashboard.results_dashboard`) renders a sequence of
Plotly bar charts. Out of the box Plotly paints every bar in one flat blue, so
the read-out looks monochrome and undifferentiated. This module is the *single
source* of the dashboard's colour language: every chart pulls its palette from
here so the page reads as one cohesive, brand-aligned design instead of a stack
of identical blue bars.

It exposes a qualitative palette plus two colour *scales*, all keyed to the
app's indigo brand colour (``#4F46E5`` from ``.streamlit/config.toml``) and kept
to a single cool-toned family so the whole page reads as one scheme:

* :data:`PALETTE` — distinct cool-toned colours for categorical series
  (products, segment answers).
* :data:`SEQUENTIAL_INDIGO` — light→deep indigo ramp for magnitudes *and*
  ordinal intensity (importance, counts, purchase intent): bigger values render
  deeper and more saturated.
* :data:`DIVERGING` — coral→slate→teal ramp for signed values (part-worth
  utilities centred at 0): below-zero reads warm coral, above-zero cool teal.
  Coral is the one warm accent, reserved for the "worse/negative" side.

and one pure helper, :func:`style_fig`, that stamps the shared layout polish
(system font, white canvas, soft gridlines, rounded bars, branded hover label,
tidy margins) onto any figure. Everything here is Streamlit-free so it stays
importable and unit-testable, matching the ``_render_*`` convention next door.
"""

from __future__ import annotations

from typing import Any

#: Brand indigo (mirrors ``primaryColor`` in ``.streamlit/config.toml``).
BRAND = "#4F46E5"

#: Ink colour for titles and value labels (mirrors the Streamlit ``textColor``).
INK = "#1F2430"

#: System sans stack; renders crisply without bundling a web font.
FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

#: Soft gridline colour, from the app's secondary-background family.
GRID = "#ECEEF6"

#: Qualitative palette for categorical series — one cool-toned family (indigo →
#: cyan → violet → teal → blue) led by the brand indigo. Adjacent entries keep
#: enough hue/lightness contrast to stay distinguishable, while the set as a
#: whole reads as a single calm, on-brand scheme rather than a rainbow.
PALETTE: tuple[str, ...] = (
    "#4F46E5",  # indigo (brand)
    "#06B6D4",  # cyan
    "#8B5CF6",  # violet
    "#14B8A6",  # teal
    "#3B82F6",  # blue
    "#0EA5E9",  # sky
    "#6366F1",  # indigo (lighter)
    "#2DD4BF",  # teal (lighter)
)

#: Sequential indigo ramp (light → deep) for magnitude charts.
SEQUENTIAL_INDIGO: tuple[str, ...] = (
    "#EEF2FF", "#C7D2FE", "#A5B4FC", "#818CF8",
    "#6366F1", "#4F46E5", "#4338CA", "#3730A3",
)

#: Diverging coral → slate → teal ramp for signed values (centre at 0). Warm
#: coral flags the below-zero (worse) side; cool teal the above-zero (better)
#: side, keeping the single warm accent inside the cool palette's logic.
DIVERGING: tuple[str, ...] = (
    "#E11D48", "#FB7185", "#FECDD3",
    "#EEF1F6",
    "#99F6E4", "#2DD4BF", "#0D9488",
)


def style_fig(fig: Any, *, height: int | None = None) -> Any:
    """Stamp the dashboard's shared layout polish onto a Plotly figure.

    Centralises the look every results chart shares so the page feels designed
    rather than assembled: a system sans font, white canvas, soft horizontal
    gridlines, left-aligned title, rounded crisp bars, legible value labels and
    a branded hover card. The figure is mutated in place (matching Plotly's own
    ``update_layout`` style) and also returned so calls can be chained.
    """
    fig.update_layout(
        font=dict(family=FONT_FAMILY, color=INK, size=13),
        title=dict(font=dict(size=17, color=INK), x=0, xanchor="left", pad=dict(b=10)),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        colorway=list(PALETTE),
        bargap=0.28,
        margin=dict(l=8, r=24, t=52, b=8),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=BRAND, font=dict(color=INK, size=12, family=FONT_FAMILY)),
        legend=dict(title_text="", orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, showline=False)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, showline=False)
    # Rounded, gap-free-edged bars with value labels drawn outside the bar (in
    # dark ink on white) so they stay legible over any fill colour. Applies only
    # to bar traces; a no-op otherwise.
    fig.update_traces(
        marker_line_width=0,
        marker_cornerradius=6,
        textposition="outside",
        cliponaxis=False,
        textfont=dict(color=INK, size=12),
        selector=dict(type="bar"),
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig
