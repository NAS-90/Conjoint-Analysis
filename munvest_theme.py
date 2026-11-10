"""Munvest look & feel for the Streamlit dashboards (dark theme, logo, Plotly styling)."""
import streamlit as st

BG, PANEL, LINE = "#0b0f15", "#131a23", "#243040"
TXT, MUTED, ACC = "#e8eef5", "#8fa1b5", "#9fdcff"
LOGO = "data:image/png;base64,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"
COLORWAY = ["#9fdcff", "#4f9de8", "#e8b24a", "#6fd3a5", "#c792ea", "#ff8a80", "#7f8fa6", "#ffd166"]

CSS = f"""
<style>
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {{background:{BG}; color:{TXT};}}
[data-testid="stHeader"] {{background:transparent;}}
[data-testid="stSidebar"] {{background:{PANEL}; border-right:1px solid {LINE};}}
.block-container {{padding-top:1.4rem; max-width:1400px;}}
h1,h2,h3,h4 {{color:{TXT}; letter-spacing:.01em; font-weight:600;}}
h1 {{font-size:1.7rem;}}
p, label, li, span, div {{font-family:-apple-system,"Segoe UI",Roboto,sans-serif;}}
a {{color:{ACC};}}
[data-testid="stMetric"] {{background:{PANEL}; border:1px solid {LINE}; border-radius:10px; padding:.8rem 1rem;}}
[data-testid="stMetricLabel"] {{color:{MUTED};}}
[data-testid="stExpander"], [data-testid="stDataFrame"] {{border:1px solid {LINE}; border-radius:10px;}}
.stButton>button, .stDownloadButton>button {{background:#1e6fd9; color:#fff; border:0; border-radius:6px; font-weight:600;}}
.stButton>button:hover {{background:#2f82ee; color:#fff;}}
button[role="tab"] {{color:{MUTED};}} button[role="tab"][aria-selected="true"] {{color:{ACC};}}
.mv-brand {{display:flex; align-items:center; gap:.8rem; padding:.2rem 0 .9rem; border-bottom:1px solid {LINE}; margin-bottom:1rem;}}
.mv-brand img {{height:64px;}}
.mv-brand .t {{font-size:.8rem; letter-spacing:.14em; text-transform:uppercase; color:{MUTED};}}
.mv-foot {{margin-top:2.5rem; padding-top:.8rem; border-top:1px solid {LINE}; color:{MUTED}; font-size:.78rem;}}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{visibility:hidden; height:0;}}
</style>
"""


def plotly_dark(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TXT, family="-apple-system, Segoe UI, Roboto, sans-serif"),
        colorway=COLORWAY, legend=dict(font=dict(color=TXT)),
        hoverlabel=dict(bgcolor=PANEL, font_color=TXT, bordercolor=LINE),
    )
    fig.update_layout(title_font=dict(color=TXT))
    fig.update_traces(textfont=dict(color=TXT), selector=dict(type="bar"))
    fig.update_layout(legend_font_color=TXT, title_font_color=TXT, modebar=dict(bgcolor="rgba(0,0,0,0)", color=MUTED, activecolor=ACC))
    fig.update_traces(insidetextfont=dict(color=TXT), outsidetextfont=dict(color=TXT), selector=dict(type="bar"))
    fig.update_xaxes(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED), automargin=True)
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED), automargin=True)
    return fig


def _patch_plotly():
    try:
        import plotly.io as pio, plotly.graph_objects as go
        t = go.layout.Template()
        t.layout.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=TXT), colorway=COLORWAY,
                        xaxis=dict(gridcolor=LINE, zerolinecolor=LINE), yaxis=dict(gridcolor=LINE, zerolinecolor=LINE))
        pio.templates["munvest"] = t
        pio.templates.default = "munvest"
    except Exception:
        pass
    try:
        from dashboard import chart_theme as ct
        if not getattr(ct, "_mv", False):
            orig = ct.style_fig
            def style_fig(fig, *a, **k):
                return plotly_dark(orig(fig, *a, **k))
            ct.style_fig = style_fig
            ct._mv = True
    except Exception:
        pass


def install(title="Munvest Analytics"):
    """Patch st.set_page_config once so every page gets the theme."""
    if getattr(st, "_mv_installed", False):
        return
    orig = st.set_page_config
    def cfg(*a, **k):
        k.setdefault("layout", "wide")
        k["page_title"] = title
        try:
            orig(*a, **k)
        except Exception:
            pass
        apply()
    st.set_page_config = cfg
    _orig_pc = st.plotly_chart
    def _pc(fig, *a, **k):
        try:
            plotly_dark(fig)
            k.setdefault("theme", None)
        except Exception:
            pass
        return _orig_pc(fig, *a, **k)
    st.plotly_chart = _pc
    try:
        from streamlit.delta_generator import DeltaGenerator as _DG
        _orig_dg = _DG.plotly_chart
        def _dgpc(self, fig, *a, **k):
            try:
                plotly_dark(fig)
                k.setdefault("theme", None)
            except Exception:
                pass
            return _orig_dg(self, fig, *a, **k)
        _DG.plotly_chart = _dgpc
    except Exception:
        pass
    st._mv_installed = True
    _patch_plotly()


def apply():
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        import munvest_pages
        st.markdown(munvest_pages.CSS, unsafe_allow_html=True)
    except Exception:
        pass


def header(subtitle):
    st.markdown(f'<div class="mv-brand"><img src="{LOGO}"><span class="t">{subtitle}</span></div>', unsafe_allow_html=True)


def footer():
    st.markdown('<div class="mv-foot">Munvest &middot; Munich &middot; Demo data for illustration &middot; <a href="https://munvest.com">munvest.com</a></div>', unsafe_allow_html=True)
