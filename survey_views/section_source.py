"""Product-agnostic source for the non-attribute survey sections (A & C).

The attribute-based sections (B0/B1/B2/B4/B5) are already table-driven: they read
the generated ``questionnaire_spec.json``. Part A (background profiling) and Part
C (willingness-to-pay) are *not* product features, so they live in a sibling
``survey_questions.json`` — one per product — authored from a ``Survey_questions``
Excel sheet (see :mod:`conjoint.generate_survey_questions`).

This module is the thin runtime adapter:

* defines the immutable :class:`ProfileQuestion` / :class:`WtpFeature` types and
  the built-in defaults (the smartphone questions, used as a fallback);
* loads ``survey_questions.json`` if present and valid, else falls back to the
  defaults — so a product with no questions file still gets a working survey.

Loading is *fail-soft*: a missing or malformed file logs a warning and returns
the defaults rather than crashing the respondent-facing app. Per-section: if the
file omits ``background`` or ``wtp``, that section falls back on its own.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Repo root (this file lives in ``<root>/survey_views/``).
ROOT = Path(__file__).resolve().parent.parent
#: Sibling of ``questionnaire_spec.json`` holding the Part A / Part C questions.
DEFAULT_QUESTIONS_PATH = ROOT / "survey_questions.json"


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
# Built-in defaults (smartphone) — also the fallback when no file is present
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
# Parsing (validation at the boundary — never trust the file)
# ---------------------------------------------------------------------------
def _parse_background(raw: object) -> tuple[ProfileQuestion, ...]:
    """Validate the ``background`` block into :class:`ProfileQuestion` items."""
    if not isinstance(raw, list):
        raise ValueError("'background' must be a list")
    questions: list[ProfileQuestion] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each background question must be an object")
        identifier = str(item["id"]).strip()
        prompt = str(item["prompt"]).strip()
        options = tuple(str(o).strip() for o in item.get("options", []) if str(o).strip())
        if not identifier or not prompt:
            raise ValueError("background question needs a non-empty id and prompt")
        if identifier in seen:
            raise ValueError(f"duplicate background question id {identifier!r}")
        if len(options) < 2:
            raise ValueError(f"background question {identifier!r} needs >=2 options")
        multi = str(item.get("input_type", "single")).strip().lower() == "multi"
        seen.add(identifier)
        questions.append(
            ProfileQuestion(identifier, prompt, options, multi, str(item.get("help", "")))
        )
    if not questions:
        raise ValueError("'background' is empty")
    return tuple(questions)


def _parse_wtp_features(raw: object) -> tuple[WtpFeature, ...]:
    """Validate the ``wtp.features`` block into :class:`WtpFeature` items."""
    if not isinstance(raw, list):
        raise ValueError("'wtp.features' must be a list")
    features: list[WtpFeature] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each wtp feature must be an object")
        identifier = str(item["id"]).strip()
        label = str(item["label"]).strip()
        if not identifier or not label:
            raise ValueError("wtp feature needs a non-empty id and label")
        if identifier in seen:
            raise ValueError(f"duplicate wtp feature id {identifier!r}")
        seen.add(identifier)
        features.append(WtpFeature(identifier, label))
    if not features:
        raise ValueError("'wtp.features' is empty")
    return tuple(features)


def _parse_amount_bands(raw: object) -> tuple[tuple[str, str], ...]:
    """Validate the ``wtp.amount_bands`` block into (code, label) pairs."""
    if not isinstance(raw, list):
        raise ValueError("'wtp.amount_bands' must be a list")
    bands: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            raise ValueError("each amount band must be a [code, label] pair")
        code, label = str(item[0]).strip(), str(item[1]).strip()
        if not code or not label or code in seen:
            raise ValueError(f"invalid or duplicate amount band code {code!r}")
        seen.add(code)
        bands.append((code, label))
    if len(bands) < 2:
        raise ValueError("'wtp.amount_bands' needs >=2 bands")
    return tuple(bands)


# ---------------------------------------------------------------------------
# Public loaders (fail-soft to defaults)
# ---------------------------------------------------------------------------
def _load_document(path: Path | None) -> dict:
    """Read+parse the questions JSON; return ``{}`` if absent/unreadable."""
    target = path or DEFAULT_QUESTIONS_PATH
    if not Path(target).exists():
        return {}
    try:
        payload = json.loads(Path(target).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Could not read %s (%s) — using built-in defaults", target, exc)
        return {}
    if not isinstance(payload, dict):
        logger.warning("%s is not a JSON object — using built-in defaults", target)
        return {}
    return payload


def load_background_questions(path: Path | None = None) -> tuple[ProfileQuestion, ...]:
    """Part A questions from ``survey_questions.json`` or the built-in defaults."""
    document = _load_document(path)
    if "background" not in document:
        return DEFAULT_PROFILE_QUESTIONS
    try:
        return _parse_background(document["background"])
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Invalid 'background' section (%s) — using defaults", exc)
        return DEFAULT_PROFILE_QUESTIONS


def load_wtp_features(path: Path | None = None) -> tuple[WtpFeature, ...]:
    """Part C upgrade features from ``survey_questions.json`` or the defaults."""
    wtp = _load_document(path).get("wtp")
    if not isinstance(wtp, dict) or "features" not in wtp:
        return DEFAULT_WTP_FEATURES
    try:
        return _parse_wtp_features(wtp["features"])
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Invalid 'wtp.features' (%s) — using defaults", exc)
        return DEFAULT_WTP_FEATURES


def load_amount_bands(path: Path | None = None) -> tuple[tuple[str, str], ...]:
    """Part C amount bands from ``survey_questions.json`` or the defaults."""
    wtp = _load_document(path).get("wtp")
    if not isinstance(wtp, dict) or "amount_bands" not in wtp:
        return DEFAULT_AMOUNT_BANDS
    try:
        return _parse_amount_bands(wtp["amount_bands"])
    except (ValueError, TypeError) as exc:
        logger.warning("Invalid 'wtp.amount_bands' (%s) — using defaults", exc)
        return DEFAULT_AMOUNT_BANDS
