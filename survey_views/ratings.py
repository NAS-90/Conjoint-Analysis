"""B1 — single-page-per-attribute desirability ratings.

The respondent rates how desirable each level of each active attribute is, on
the spec's 1..5 scale, one attribute per screen. These ratings are an early
preference signal: they seed the ideal **anchor** (derived in B2) that drives the
B4 comparisons, and they are recorded into the responses CSV (stage ``rating``)
by the summary page. They are *not* the final conjoint utilities.

All rating data is stored under stage ``ratings`` via the shared sequential
controller; on Finish the flow advances to B2 (deal-breakers).
"""

from __future__ import annotations

import streamlit as st

from conjoint.questionnaire import AttributeQuestion, QuestionnaireSpec
from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    record_answer,
    render_sequence,
)
from survey_views.spec_source import attribute_display_name, load_spec
from survey_views.state import B2_PAGE_KEY
from survey_views.theme import apply_base_theme, flow_header, safe_md

#: Stage identifier under which per-attribute answers are stored
#: (``stage_answers("ratings")[attribute_name] = {level_code: rating}``).
STAGE = "ratings"


def _attribute_step(spec: QuestionnaireSpec, attr: AttributeQuestion) -> Step:
    """Build a :class:`Step` that renders one attribute's level ratings."""
    scale = spec.scale
    options = list(range(int(scale.min), int(scale.max) + 1))

    def render() -> bool:
        prior = get_answer(STAGE, attr.feature_name, default={}) or {}
        if not isinstance(prior, dict):
            prior = {}

        if attr.description:
            st.caption(attr.description)
        st.write(attr.prompt)
        st.caption(f"{scale.min} = least desirable · {scale.max} = most desirable")

        ratings: dict[str, int] = {}
        for level in attr.levels:
            previous = prior.get(level.code)
            try:
                default_index = options.index(int(previous)) if previous is not None else None
            except (TypeError, ValueError):
                default_index = None
            value = st.radio(
                f"**{safe_md(level.label)}**",
                options=options,
                index=default_index,
                horizontal=True,
                key=f"survey_rating__{attr.feature_name}__{level.code}",
            )
            if value is not None:
                ratings[level.code] = int(value)

        record_answer(STAGE, attr.feature_name, ratings)
        return len(ratings) == len(attr.levels)

    return Step(
        identifier=attr.feature_name,
        title=attribute_display_name(attr.feature_name),
        render=render,
    )


def render_questionnaire() -> None:
    """Render B1 (one attribute per screen, all active attributes)."""
    apply_base_theme()
    flow_header(
        3,
        7,
        "Rate each feature",
        "Say how appealing each option is. There are no right answers.",
    )

    spec = load_spec()
    if spec is None:
        return

    active = spec.active_attributes
    if not active:
        st.warning("There are no questions to answer right now.")
        return

    st.caption(
        f"Rate each option from {spec.scale.min} (least desirable) to "
        f"{spec.scale.max} (most desirable). {len(active)} features to rate."
    )

    steps = tuple(_attribute_step(spec, attr) for attr in active)

    def on_complete() -> None:
        advance_to(B2_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Feature")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run`` of the page
    render_questionnaire()
