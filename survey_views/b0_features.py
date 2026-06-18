"""B0 — feature explanation.

Product attributes often carry technical terms (processor tiers, RAM, capacities,
and the like). If a respondent doesn't understand them the later choice data is
unreliable, so this section explains every attribute and its levels *before* the
preference questions. It is purely informational — no answers are recorded — and
is built entirely from the loaded :class:`QuestionnaireSpec` so it stays in sync
with the active attributes.

On "I'm ready" the flow advances to B2 (deal-breakers).
"""

from __future__ import annotations

import streamlit as st

from survey_views.navigation import advance_to
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import B2_PAGE_KEY
from survey_views.theme import apply_base_theme, flow_header


def render_features_intro() -> None:
    """Render B0 (a spec-driven guide to every attribute + its levels)."""
    apply_base_theme()
    spec = load_spec()
    if spec is None:
        return

    flow_header(
        2,
        6,
        "About the features",
        "A quick guide to the features you'll be asked about next.",
    )

    active = spec.active_attributes
    if not active:
        st.warning("There are no features to describe right now.")
        return

    labels = level_label_map(spec)
    for attr in active:
        with st.container(border=True):
            st.markdown(f"#### {attribute_display_name(attr.feature_name)}")
            if attr.description:
                st.caption(attr.description)
            for level in attr.levels:
                st.markdown(
                    f"- {format_level(labels, attr.feature_name, level.code)}"
                )

    st.caption(f"{len(active)} features, explained. Take your time.")
    if st.button("I'm ready →", type="primary"):
        advance_to(B2_PAGE_KEY)


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_features_intro()
