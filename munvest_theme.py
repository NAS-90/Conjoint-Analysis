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
.mv-brand img {{height:34px;}}
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
    fig.update_xaxes(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickfont=dict(color=MUTED))
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
    st._mv_installed = True
    _patch_plotly()


def apply():
    st.markdown(CSS, unsafe_allow_html=True)


def header(subtitle):
    st.markdown(f'<div class="mv-brand"><img src="{LOGO}"><span class="t">{subtitle}</span></div>', unsafe_allow_html=True)


def footer():
    st.markdown('<div class="mv-foot">Munvest UG &middot; Munich &middot; Demo data for illustration &middot; <a href="https://munvest.com">munvest.com</a></div>', unsafe_allow_html=True)
