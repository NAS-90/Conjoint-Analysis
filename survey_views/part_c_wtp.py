"""Part C — willingness-to-pay / surcharge.

The reference design closes with surcharge questions: would the respondent pay
*extra* for specific upgrades? This is a lightweight, ACBC-flavoured section — it
doesn't enter core utility estimation, but it tells us whether a respondent not
only *likes* a feature but would pay more for it (price sensitivity / business
value).

One upgrade per screen, each answered with an amount band. Answers are recorded
into the responses CSV (stage ``wtp``); on Finish the flow advances to the final
Thank-you page.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    record_answer,
    render_sequence,
)
from survey_views.state import ACBC_SUMMARY_PAGE_KEY
from survey_views.theme import apply_base_theme, flow_header, safe_md

#: Stage identifier under which Part C answers are stored.
STAGE = "wtp"


@dataclass(frozen=True)
class WtpFeature:
    """One upgrade the respondent might pay extra for."""

    identifier: str
    label: str


#: The upgrades probed in Part C (smartphone reframing of the reference design).
WTP_FEATURES: tuple[WtpFeature, ...] = (
    WtpFeature("camera", "A much better camera (108 MP+)"),
    WtpFeature("battery", "Much longer battery life (6 000 mAh+)"),
    WtpFeature("charging", "Much faster charging"),
    WtpFeature("memory", "More memory & storage (12 GB / 256 GB+)"),
    WtpFeature("display", "A larger, smoother display"),
    WtpFeature("connectivity", "5G connectivity"),
)

#: Amount bands (stored code → respondent-facing label).
AMOUNT_BANDS: tuple[tuple[str, str], ...] = (
    ("none", "Nothing extra"),
    ("up_to_50", "Up to $50 more"),
    ("up_to_100", "Up to $100 more"),
    ("150_plus", "$150 or more"),
)
_BAND_CODES: tuple[str, ...] = tuple(code for code, _ in AMOUNT_BANDS)
_BAND_LABELS: dict[str, str] = {code: label for code, label in AMOUNT_BANDS}


def _feature_step(feature: WtpFeature) -> Step:
    """One :class:`Step` asking the amount band for a single upgrade."""

    def render() -> bool:
        st.write(f"How much extra would you pay for **{safe_md(feature.label)}**?")
        prior = get_answer(STAGE, feature.identifier)
        index = _BAND_CODES.index(prior) if prior in _BAND_CODES else None
        choice = st.radio(
            "Extra you'd pay",
            options=list(_BAND_CODES),
            index=index,
            format_func=lambda code: _BAND_LABELS[code],
            key=f"wtp__{feature.identifier}",
            label_visibility="collapsed",
        )
        if choice is None:
            return False
        record_answer(STAGE, feature.identifier, str(choice))
        return True

    return Step(identifier=feature.identifier, title=feature.label, render=render)


def render_wtp() -> None:
    """Render Part C (one upgrade per screen)."""
    apply_base_theme()
    flow_header(
        7,
        7,
        "Paying a bit extra",
        "Almost done — tell us which upgrades would be worth paying more for.",
    )

    steps = tuple(_feature_step(feature) for feature in WTP_FEATURES)

    def on_complete() -> None:
        advance_to(ACBC_SUMMARY_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Upgrade")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_wtp()
