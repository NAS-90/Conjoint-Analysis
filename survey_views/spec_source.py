"""Resolve a :class:`QuestionnaireSpec` for the survey app.

The survey ships with a committed ``questionnaire_spec.json`` (generated from
``conjoint_demo.xlsx`` via ``python -m conjoint.generate_questionnaire``). The
respondent-facing app loads this bundled spec silently — no facilitator UI is
rendered so the sidebar stays clean for the respondent.

Facilitators can run **any product** without editing the committed default by
pointing the ``SURVEY_SPEC`` env var at that product's spec JSON (mirrors
``section_source``'s ``SURVEY_WORKBOOK``), by passing ``?spec=<path>`` as a query
parameter, or by replacing ``questionnaire_spec.json`` on disk.

All non-trivial logic lives in :mod:`conjoint.questionnaire`; this module is the
thin Streamlit-facing adapter.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from conjoint import questionnaire as q
from conjoint.questionnaire import QuestionnaireSpec
from survey_views.theme import safe_md

#: Repo root (this file lives in ``<root>/survey_views/``).
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = ROOT / "questionnaire_spec.json"
#: Env-var override for the active spec (mirrors ``section_source.SURVEY_WORKBOOK``),
#: so any product can be served without overwriting the committed default.
SPEC_ENV_VAR = "SURVEY_SPEC"


@st.cache_data(show_spinner=False)
def _spec_dict_from_workbook(workbook_bytes: bytes, name: str) -> dict:
    """Build a spec dict from uploaded workbook bytes (cached by content)."""
    suffix = Path(name).suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(workbook_bytes)
        tmp_path = Path(handle.name)
    try:
        spec = q.build_questionnaire(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return q.spec_to_dict(spec)


def _spec_path_override() -> Path | None:
    """Optional ``?spec=<path>`` query-param override for facilitators."""
    try:
        params = st.query_params
    except Exception:
        return None
    raw = params.get("spec") if hasattr(params, "get") else None
    if not raw:
        return None
    return Path(str(raw))


def _resolve_spec_path() -> Path:
    """Active spec path, most specific first.

    ``?spec=<path>`` query param → ``$SURVEY_SPEC`` env var → bundled
    :data:`DEFAULT_SPEC`. The env var lets a facilitator serve any product
    without touching the committed default file.
    """
    override = _spec_path_override()
    if override is not None:
        return override
    env_path = os.environ.get(SPEC_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_SPEC


def load_spec() -> QuestionnaireSpec | None:
    """Load the active questionnaire spec (respondent-facing — no sidebar UI).

    Returns ``None`` (after a silent error) if the spec file cannot be found,
    so callers can early-return without crashing the page.
    """
    spec_path = _resolve_spec_path()
    if not Path(spec_path).exists():
        st.error(
            "The questionnaire is not configured yet. Please contact the survey "
            "administrator."
        )
        return None
    return q.read_spec(spec_path)


# ---------------------------------------------------------------------------
# Respondent-facing display helpers
# ---------------------------------------------------------------------------
def level_label_map(spec: QuestionnaireSpec) -> dict[str, dict[str, str]]:
    """Return ``{attribute: {level_code: level_label}}`` from a spec.

    Used by the ACBC pages to render internal level codes as the human-friendly
    labels respondents originally saw.
    """
    return {
        attr.feature_name: {level.code: level.label for level in attr.levels}
        for attr in spec.attributes
    }


def attribute_display_name(feature_name: str) -> str:
    """Title-case a ``feature_name`` for respondent-facing headings.

    Single-word identifiers like ``ram``/``os`` become ``RAM``/``OS`` (treated
    as acronyms when short), longer ones are simply title-cased.
    """
    cleaned = feature_name.replace("_", " ").strip()
    if not cleaned:
        return feature_name
    if " " not in cleaned and len(cleaned) <= 3:
        return cleaned.upper()
    return cleaned.title()


def format_level(
    labels: dict[str, dict[str, str]], attribute: str, code: str
) -> str:
    """Look up a level label (markdown-safe), falling back to the code.

    The label is routed through :func:`survey_views.theme.safe_md` so price
    labels like "$300 – $700" render literally instead of as LaTeX math.
    """
    return safe_md(labels.get(attribute, {}).get(code, code))
