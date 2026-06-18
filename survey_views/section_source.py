"""Product-agnostic source for the non-attribute survey sections (A & C).

The attribute-based sections (B0/B1/B2/B4/B5) read the generated
``questionnaire_spec.json``. Part A (background profiling) and Part C
(willingness-to-pay) are *not* product features, so they are authored in a
``Survey_questions`` sheet of a per-product workbook and read **directly from
that Excel file at runtime** — no intermediate JSON artifact.

Sheet schema (one row per question; blank rows ignored):

==========  ===============================================================
column      meaning
==========  ===============================================================
section     ``A`` (background) / ``C`` (WTP feature) / ``bands`` (amount band)
id          stable identifier / band code (e.g. ``budget``, ``up_to_50``)
prompt      question text (A), upgrade label (C), or band label (bands)
input_type  ``single`` or ``multi`` (Part A only; ignored elsewhere)
options     ``;``-separated choices (Part A only)
help        optional caption (Part A only)
==========  ===============================================================

Workbook resolution (first that exists wins): an explicit path argument, the
``SURVEY_WORKBOOK`` env var, else the conventional ``survey_questions.xlsx`` next
to the spec. Loading is *fail-soft*: a missing/unreadable file, a missing sheet
or an invalid section logs a warning and falls back to the built-in defaults —
so the respondent-facing app never crashes, and a product with no questions
workbook still gets a working survey.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

#: Repo root (this file lives in ``<root>/survey_views/``).
ROOT = Path(__file__).resolve().parent.parent
#: Conventional per-product workbook holding the ``Survey_questions`` sheet.
DEFAULT_WORKBOOK = ROOT / "survey_questions.xlsx"
#: Sheet name read for Part A / Part C.
SHEET = "Survey_questions"

#: Accepted ``section`` aliases → canonical kind.
_BACKGROUND = {"a", "a_general", "background", "profiling"}
_WTP = {"c", "c_wtp", "wtp", "surcharge"}
_BANDS = {"band", "bands", "amount", "amount_band", "amount_bands"}

#: Exceptions that mean "use the defaults" (missing file/sheet, bad data, no engine).
_FALLBACK_ERRORS = (OSError, ValueError, KeyError, ImportError)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProfileQuestion:
    """One Part A profiling question."""

    identifier: str
    prompt: str
    options: tuple[str, ...]
    multi: bool = False
    help: str = ""


@dataclass(frozen=True)
class WtpFeature:
    """One Part C upgrade the respondent might pay extra for."""

    identifier: str
    label: str


# ---------------------------------------------------------------------------
# Built-in defaults (smartphone) — also the fallback when no workbook is present
# ---------------------------------------------------------------------------
DEFAULT_PROFILE_QUESTIONS: tuple[ProfileQuestion, ...] = (
    ProfileQuestion(
        "purchase_timing",
        "When are you most likely to buy your next smartphone?",
        ("Within 3 months", "3–12 months", "More than a year", "No plans yet"),
    ),
    ProfileQuestion(
        "current_brand",
        "Which brand is your current phone?",
        (
            "Apple",
            "Samsung",
            "Xiaomi",
            "Huawei",
            "Google",
            "Another brand",
            "I don't have one",
        ),
    ),
    ProfileQuestion(
        "budget",
        "Roughly what budget do you have in mind?",
        ("Under $300", "$300 – $700", "Over $700", "Not sure yet"),
    ),
    ProfileQuestion(
        "usage",
        "What do you mainly use your phone for?",
        (
            "Calls & messaging",
            "Social media",
            "Photography",
            "Gaming",
            "Work & productivity",
            "Streaming video",
        ),
        multi=True,
        help="Choose all that apply.",
    ),
    ProfileQuestion(
        "top_factor",
        "What matters most to you when choosing a phone?",
        ("Price", "Performance", "Camera", "Battery life", "Brand", "Screen"),
    ),
)

DEFAULT_WTP_FEATURES: tuple[WtpFeature, ...] = (
    WtpFeature("camera", "A much better camera (108 MP+)"),
    WtpFeature("battery", "Much longer battery life (6 000 mAh+)"),
    WtpFeature("charging", "Much faster charging"),
    WtpFeature("memory", "More memory & storage (12 GB / 256 GB+)"),
    WtpFeature("display", "A larger, smoother display"),
    WtpFeature("connectivity", "5G connectivity"),
)

#: Amount bands (stored code → respondent-facing label). Shared across Part C.
DEFAULT_AMOUNT_BANDS: tuple[tuple[str, str], ...] = (
    ("none", "Nothing extra"),
    ("up_to_50", "Up to $50 more"),
    ("up_to_100", "Up to $100 more"),
    ("150_plus", "$150 or more"),
)


# ---------------------------------------------------------------------------
# Workbook reading + row parsing (validation at the boundary)
# ---------------------------------------------------------------------------
def _resolve_workbook(explicit: Path | str | None) -> Path | None:
    """First existing of: explicit arg → ``$SURVEY_WORKBOOK`` → default file."""
    for candidate in (explicit, os.environ.get("SURVEY_WORKBOOK"), DEFAULT_WORKBOOK):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _cell(row: dict, key: str, default: str = "") -> str:
    """Trimmed string cell (blank for NaN/None/missing)."""
    value = row.get(key, default)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip()


def _split_options(raw: object) -> list[str]:
    """Split a ``;``-separated options cell into trimmed, non-empty parts."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    return [part.strip() for part in str(raw).split(";") if part.strip()]


def _read_rows(workbook: Path) -> list[dict]:
    """Read the ``Survey_questions`` sheet into a list of row dicts."""
    frame = pd.read_excel(workbook, sheet_name=SHEET)
    return frame.to_dict("records")


def _parse_background(rows: list[dict]) -> tuple[ProfileQuestion, ...]:
    """``section=A`` rows → :class:`ProfileQuestion` items (raises on invalid)."""
    questions: list[ProfileQuestion] = []
    seen: set[str] = set()
    for row in rows:
        if _cell(row, "section").lower() not in _BACKGROUND:
            continue
        identifier = _cell(row, "id")
        if not identifier:
            continue
        prompt = _cell(row, "prompt")
        options = tuple(_split_options(row.get("options")))
        if not prompt or len(options) < 2:
            raise ValueError(f"background question {identifier!r} needs a prompt and >=2 options")
        if identifier in seen:
            raise ValueError(f"duplicate background id {identifier!r}")
        seen.add(identifier)
        multi = _cell(row, "input_type", "single").lower() == "multi"
        questions.append(
            ProfileQuestion(identifier, prompt, options, multi, _cell(row, "help"))
        )
    return tuple(questions)


def _parse_wtp_features(rows: list[dict]) -> tuple[WtpFeature, ...]:
    """``section=C`` rows → :class:`WtpFeature` items (raises on invalid)."""
    features: list[WtpFeature] = []
    seen: set[str] = set()
    for row in rows:
        if _cell(row, "section").lower() not in _WTP:
            continue
        identifier = _cell(row, "id")
        if not identifier:
            continue
        label = _cell(row, "prompt")
        if not label:
            raise ValueError(f"wtp feature {identifier!r} needs a label (prompt)")
        if identifier in seen:
            raise ValueError(f"duplicate wtp id {identifier!r}")
        seen.add(identifier)
        features.append(WtpFeature(identifier, label))
    return tuple(features)


def _parse_amount_bands(rows: list[dict]) -> tuple[tuple[str, str], ...]:
    """``section=bands`` rows → (code, label) pairs (raises on invalid)."""
    bands: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if _cell(row, "section").lower() not in _BANDS:
            continue
        code = _cell(row, "id")
        if not code:
            continue
        label = _cell(row, "prompt")
        if not label:
            raise ValueError(f"amount band {code!r} needs a label (prompt)")
        if code in seen:
            raise ValueError(f"duplicate amount band code {code!r}")
        seen.add(code)
        bands.append((code, label))
    if bands and len(bands) < 2:
        raise ValueError("amount bands need >=2 entries")
    return tuple(bands)


# ---------------------------------------------------------------------------
# Public loaders (fail-soft to defaults)
# ---------------------------------------------------------------------------
def load_background_questions(workbook: Path | str | None = None) -> tuple[ProfileQuestion, ...]:
    """Part A questions from the workbook's sheet, or the built-in defaults."""
    target = _resolve_workbook(workbook)
    if target is None:
        return DEFAULT_PROFILE_QUESTIONS
    try:
        questions = _parse_background(_read_rows(target))
    except _FALLBACK_ERRORS as exc:
        logger.warning("Could not read Part A from %s (%s) — using defaults", target, exc)
        return DEFAULT_PROFILE_QUESTIONS
    return questions or DEFAULT_PROFILE_QUESTIONS


def load_wtp_features(workbook: Path | str | None = None) -> tuple[WtpFeature, ...]:
    """Part C upgrade features from the workbook's sheet, or the defaults."""
    target = _resolve_workbook(workbook)
    if target is None:
        return DEFAULT_WTP_FEATURES
    try:
        features = _parse_wtp_features(_read_rows(target))
    except _FALLBACK_ERRORS as exc:
        logger.warning("Could not read Part C from %s (%s) — using defaults", target, exc)
        return DEFAULT_WTP_FEATURES
    return features or DEFAULT_WTP_FEATURES


def load_amount_bands(workbook: Path | str | None = None) -> tuple[tuple[str, str], ...]:
    """Part C amount bands from the workbook's sheet, or the defaults."""
    target = _resolve_workbook(workbook)
    if target is None:
        return DEFAULT_AMOUNT_BANDS
    try:
        bands = _parse_amount_bands(_read_rows(target))
    except _FALLBACK_ERRORS as exc:
        logger.warning("Could not read amount bands from %s (%s) — using defaults", target, exc)
        return DEFAULT_AMOUNT_BANDS
    return bands or DEFAULT_AMOUNT_BANDS
