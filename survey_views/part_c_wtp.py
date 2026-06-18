"""Part C — willingness-to-pay / surcharge.

The reference design closes with surcharge questions: would the respondent pay
*extra* for specific upgrades? This is a lightweight, ACBC-flavoured section — it
doesn't enter core utility estimation, but it tells us whether a respondent not
only *likes* a feature but would pay more for it (price sensitivity / business
value).

One upgrade per screen, each answered with an amount band. The upgrade list and
amount bands are product-driven (loaded via :mod:`survey_views.section_source`,
with built-in defaults). Answers are recorded into the responses CSV (stage
``wtp``); on Finish the flow advances to the final Thank-you page.
"""

from __future__ import annotations

import streamlit as st

from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    record_answer,
    render_sequence,
)
from survey_views.section_source import (
    DEFAULT_AMOUNT_BANDS,
    DEFAULT_WTP_FEATURES,
    WtpFeature,
    load_amount_bands,
    load_wtp_features,
)
from survey_views.state import ACBC_SUMMARY_PAGE_KEY
from survey_views.theme import apply_base_theme, flow_header, safe_md

#: Stage identifier under which Part C answers are stored.
STAGE = "wtp"

#: Built-in defaults (used when ``survey_questions.json`` is absent). Re-exported
#: for back-compat; live values come from :mod:`survey_views.section_source`.
WTP_FEATURES: tuple[WtpFeature, ...] = DEFAULT_WTP_FEATURES
AMOUNT_BANDS: tuple[tuple[str, str], ...] = DEFAULT_AMOUNT_BANDS


def _feature_step(
    feature: WtpFeature, band_codes: tuple[str, ...], band_labels: dict[str, str]
) -> Step:
    """One :class:`Step` asking the amount band for a single upgrade."""

    def render() -> bool:
        st.write(f"How much extra would you pay for **{safe_md(feature.label)}**?")
        prior = get_answer(STAGE, feature.identifier)
        index = band_codes.index(prior) if prior in band_codes else None
        choice = st.radio(
            "Extra you'd pay",
            options=list(band_codes),
            index=index,
            format_func=lambda code: band_labels[code],
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
        6,
        6,
        "Paying a bit extra",
        "Almost done — tell us which upgrades would be worth paying more for.",
    )

    bands = load_amount_bands()
    band_codes = tuple(code for code, _ in bands)
    band_labels = {code: label for code, label in bands}

    steps = tuple(
        _feature_step(feature, band_codes, band_labels)
        for feature in load_wtp_features()
    )

    def on_complete() -> None:
        advance_to(ACBC_SUMMARY_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Upgrade")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_wtp()
