"""Shared visual theme + small render helpers for the survey app.

The survey is respondent-facing, so every page calls :func:`apply_base_theme`
once at the top to inject a consistent, polished look: a focused content
column, soft elevated cards, radio options that read as selectable cards, a
slim brand progress bar, and a clean respondent view with the developer
toolbar hidden. The base colour palette / font live in ``.streamlit/config.toml``;
this module adds the refinement CSS the theme config can't express.

Three helpers keep the per-page code thin:

* :func:`flow_header` — a consistent "Step X of N · <title>" banner used by the
  ACBC stage pages so respondents always know where they are.
* :func:`expect_steps` — the numbered "what to expect" list on the Welcome
  page (replaces the old emoji bullet list).
* :func:`safe_md` — escapes characters Streamlit's Markdown renderer would
  otherwise interpret. The important one is ``$``: a pair of dollar signs is
  treated as inline LaTeX, which mangles price labels like "$300 – $700".
"""

from __future__ import annotations

import html
from typing import Iterable

import streamlit as st

_BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --brand: #4F46E5;
    --brand-strong: #4338CA;
    --brand-tint: #F1F1FE;
    --ink: #1F2430;
    --muted: #5B6172;
    --line: #E7E8F2;
    --card-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 8px 24px rgba(16, 24, 40, 0.05);
}

/* A clean, consistent typeface (graceful system fallback). Scoped to the app
   shell so text inherits Inter, while Streamlit's Material Symbols icon font
   (which sets its own family on the icon spans) keeps rendering glyphs. */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
        Helvetica, Arial, sans-serif;
}
button, input, textarea { font-family: inherit; }

/* Respondent-clean chrome: drop the developer toolbar / menu / footer. */
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }

/* Focused, comfortable content column. */
.block-container { padding-top: 2.75rem; padding-bottom: 5rem; max-width: 760px; }

/* Sidebar polish. */
[data-testid="stSidebar"] { background: #FBFBFE; border-right: 1px solid var(--line); }

/* Typography. */
h1 { font-size: 2rem; font-weight: 700; letter-spacing: -0.025em; color: var(--ink); }
h2 { font-weight: 700; letter-spacing: -0.02em; color: var(--ink); }
h3 { font-weight: 650; letter-spacing: -0.012em; color: var(--ink); }
p, li, label { color: var(--ink); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
    color: var(--muted) !important;
}

/* Lead paragraph (Welcome intro). */
p.lead { font-size: 1.08rem; line-height: 1.6; color: var(--muted); margin: 0.35rem 0 0.5rem; }

/* Bordered containers → soft, elevated cards. */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px;
    border: 1px solid var(--line) !important;
    box-shadow: var(--card-shadow);
    background: #FFFFFF;
}

/* Buttons: rounded, full-width within their slot, with a gentle hover lift. */
.stButton > button, .stDownloadButton > button {
    border-radius: 11px;
    padding: 0.62rem 1.1rem;
    font-weight: 600;
    width: 100%;
    border: 1px solid var(--line);
    transition: transform .12s ease, box-shadow .12s ease, background .12s ease,
        border-color .12s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); }
.stButton > button:active, .stDownloadButton > button:active { transform: translateY(0); }
button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background: var(--brand);
    border-color: var(--brand);
    color: #FFFFFF;
    box-shadow: 0 1px 2px rgba(79, 70, 229, 0.25);
}
button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
    background: var(--brand-strong);
    border-color: var(--brand-strong);
    box-shadow: 0 6px 16px rgba(79, 70, 229, 0.30);
}
button[kind="secondary"] { background: #FFFFFF; color: #3A3F4B; }
button[kind="secondary"]:hover { border-color: #C7C9DE; background: #FAFAFE; }
.stButton > button:disabled, .stDownloadButton > button:disabled {
    opacity: .55; transform: none; box-shadow: none; cursor: not-allowed;
}

/* Slim, rounded progress bar in the brand colour. */
[data-testid="stProgress"] { margin: 0.15rem 0 0.35rem; }
[data-testid="stProgress"] div[role="progressbar"] { background: #ECEDF7 !important; border-radius: 999px; }
[data-testid="stProgress"] div[role="progressbar"] > div {
    background: linear-gradient(90deg, #6366F1, var(--brand));
    border-radius: 999px;
}

/* Text input. */
div[data-baseweb="input"], div[data-baseweb="base-input"] { border-radius: 10px; }
div[data-baseweb="input"]:focus-within {
    border-color: var(--brand) !important;
    box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12);
}

/* Radio options read as selectable cards (the survey's core interaction). */
[data-testid="stRadio"] > div[role="radiogroup"] { gap: 8px; }
[data-testid="stRadio"] label[data-baseweb="radio"] {
    border: 1.5px solid var(--line);
    border-radius: 12px;
    padding: 0.65rem 0.85rem;
    margin: 0;
    background: #FFFFFF;
    align-items: center;
    cursor: pointer;
    transition: border-color .12s ease, background .12s ease, box-shadow .12s ease;
}
[data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    border-color: #C5C4F2;
    background: #FAFAFF;
}
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
    border-color: var(--brand);
    background: var(--brand-tint);
    box-shadow: inset 0 0 0 1px var(--brand);
}

/* Flow header banner. */
.survey-flowhead { margin: 0 0 1.25rem; }
.survey-step {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--brand);
    background: var(--brand-tint);
    padding: 4px 11px;
    border-radius: 999px;
    margin-bottom: 0.6rem;
}
.survey-flowhead h2 { margin: 0.15rem 0 0.3rem; }
.survey-flowhead p { color: var(--muted); margin: 0; font-size: 1.02rem; }

/* "What to expect" numbered steps (Welcome). */
.expect { display: flex; flex-direction: column; gap: 0.85rem; margin: 0.4rem 0 0.2rem; }
.expect-row { display: flex; gap: 0.8rem; align-items: flex-start; }
.expect-num {
    flex: none;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: var(--brand-tint);
    color: var(--brand);
    font-weight: 700;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 1px;
}
.expect-t { font-weight: 600; color: var(--ink); line-height: 1.3; }
.expect-d { color: var(--muted); font-size: 0.95rem; line-height: 1.45; }
</style>
"""


def apply_base_theme() -> None:
    """Inject the shared survey CSS.

    Emitted on every script run (not guarded by a session flag) so the styling
    survives Streamlit reruns — an element not produced in the current run is
    dropped from the page, so a once-per-session guard would lose the CSS after
    the first interaction.
    """
    st.markdown(_BASE_CSS, unsafe_allow_html=True)


def safe_md(text: object) -> str:
    """Escape Markdown/LaTeX-significant characters in respondent-facing text.

    Most importantly, escapes ``$`` so price labels render literally instead of
    being parsed as inline LaTeX math. Idempotent: text that already escapes its
    dollar signs is normalised first, so it is safe to call more than once.
    """
    if text is None:
        return ""
    out = str(text)
    out = out.replace("\\$", "$")  # normalise any pre-escaped dollars
    out = out.replace("$", r"\$")  # escape so $...$ is not read as LaTeX
    return out


def flow_header(step: int, total: int, title: str, subtitle: str = "") -> None:
    """Render a consistent "Step X of N · <title>" banner for a stage page."""
    subtitle_html = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f"""
        <div class="survey-flowhead">
            <span class="survey-step">Step {int(step)} of {int(total)}</span>
            <h2>{html.escape(title)}</h2>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def expect_steps(steps: Iterable[tuple[str, str]]) -> None:
    """Render a numbered "what to expect" list (title + description per step).

    Replaces the old emoji bullet list with tidy numbered badges so the Welcome
    page previews the flow without any emoji.
    """
    # Emit as a single line with no leading indentation: Streamlit's Markdown
    # renderer turns 4-space-indented lines into a code block, which would show
    # the raw HTML instead of rendering it.
    rows = "".join(
        f'<div class="expect-row"><span class="expect-num">{i}</span>'
        f'<div><div class="expect-t">{html.escape(title)}</div>'
        f'<div class="expect-d">{html.escape(description)}</div></div></div>'
        for i, (title, description) in enumerate(steps, start=1)
    )
    st.markdown(f'<div class="expect">{rows}</div>', unsafe_allow_html=True)
