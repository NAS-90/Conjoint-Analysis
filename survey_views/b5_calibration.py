"""B5 — purchase-probability calibration.

The pair comparison (B4) only reveals *which* of two options a respondent
prefers, not whether they would actually buy any of them. Calibration fills that
gap: the respondent sees a few complete concepts and gives each a 0–5 purchase
probability (0 = would definitely not buy, 5 = would definitely buy).

The concepts shown are the respondent's derived ideal (the anchor) plus a couple
of realistic near-anchor variants that satisfy their B2 constraints, generated
deterministically. Answers are recorded into the responses CSV (stage
``calibration``); on Finish the flow advances to Part C.
"""

from __future__ import annotations

import streamlit as st

from conjoint.acbc.constraints import anchor_from_ratings, filter_by_constraints
from conjoint.acbc.design import Profile, attribute_levels_from_spec
from conjoint.acbc.screener import seed_screener_pool
from conjoint.questionnaire import QuestionnaireSpec
from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    record_answer,
    render_sequence,
)
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import (
    ACBC_ANCHOR_KEY,
    MUST_HAVE_KEY,
    PART_C_PAGE_KEY,
    UNACCEPTABLE_KEY,
)
from survey_views.theme import apply_base_theme, flow_header

#: Stage identifier under which B5 probabilities are stored.
STAGE = "calibration"
#: Session key holding the concept :class:`Profile` list shown this run, so the
#: summary page can pair each answer with its concept.
CALIBRATION_CONCEPTS_KEY = "calibration_concepts"

_DEFAULT_CONCEPTS = 3
_DEFAULT_SEED = 2026
#: Purchase-probability scale (0 = definitely not, 5 = definitely).
_PROBABILITY_OPTIONS: tuple[int, ...] = (0, 1, 2, 3, 4, 5)


def _resolve_anchor(spec: QuestionnaireSpec, must_have, unacceptable) -> Profile:
    """The session anchor (from B2), or one derived from spec order as a fallback."""
    anchor = st.session_state.get(ACBC_ANCHOR_KEY)
    if isinstance(anchor, Profile):
        return anchor
    return anchor_from_ratings(
        {}, spec, must_have=must_have, unacceptable=unacceptable
    )


def calibration_concepts(
    spec: QuestionnaireSpec,
    anchor: Profile,
    *,
    must_have=None,
    unacceptable=None,
    n_concepts: int = _DEFAULT_CONCEPTS,
    seed: int = _DEFAULT_SEED,
) -> tuple[Profile, ...]:
    """Anchor + up to ``n_concepts-1`` distinct constraint-valid variants."""
    attribute_levels = attribute_levels_from_spec(spec)
    concepts: list[Profile] = [anchor]
    seen = {anchor.levels}
    try:
        pool = seed_screener_pool(
            anchor,
            attribute_levels,
            n_profiles=n_concepts * 4,
            max_changes=min(3, len(attribute_levels)),
            seed=seed,
        )
    except ValueError:
        pool = ()
    for profile in filter_by_constraints(
        pool, must_have=must_have, unacceptable=unacceptable
    ):
        if profile.levels in seen:
            continue
        seen.add(profile.levels)
        concepts.append(profile)
        if len(concepts) >= n_concepts:
            break
    return tuple(concepts)


def _concept_step(
    index: int, profile: Profile, labels: dict[str, dict[str, str]]
) -> Step:
    """One :class:`Step` rendering a concept + its 0–5 probability radio."""

    def render() -> bool:
        st.caption(
            "Imagine this option is on sale at a fair price. "
            "0 = would definitely not buy · 5 = would definitely buy."
        )
        with st.container(border=True):
            for attribute, code in profile.levels:
                st.markdown(
                    f"- **{attribute_display_name(attribute)}**: "
                    f"{format_level(labels, attribute, code)}"
                )
        prior = get_answer(STAGE, str(index))
        try:
            default_index = (
                _PROBABILITY_OPTIONS.index(int(prior)) if prior is not None else None
            )
        except (TypeError, ValueError):
            default_index = None
        choice = st.radio(
            "How likely are you to buy this option?",
            options=list(_PROBABILITY_OPTIONS),
            index=default_index,
            horizontal=True,
            key=f"calibration__{index}",
        )
        if choice is None:
            return False
        record_answer(STAGE, str(index), int(choice))
        return True

    return Step(identifier=f"concept_{index}", title=f"Option {index + 1}", render=render)


def render_calibration() -> None:
    """Render B5 (one concept per screen)."""
    apply_base_theme()
    spec = load_spec()
    if spec is None:
        return

    flow_header(
        5,
        6,
        "Would you buy it?",
        "For each option, tell us how likely you would be to buy it.",
    )

    must_have = st.session_state.get(MUST_HAVE_KEY, {}) or {}
    unacceptable = st.session_state.get(UNACCEPTABLE_KEY, {}) or {}
    anchor = _resolve_anchor(spec, must_have, unacceptable)
    concepts = calibration_concepts(
        spec, anchor, must_have=must_have, unacceptable=unacceptable
    )
    # Stash so the summary page can pair answers with their concept profiles.
    st.session_state[CALIBRATION_CONCEPTS_KEY] = concepts

    labels = level_label_map(spec)
    steps = tuple(
        _concept_step(i, profile, labels) for i, profile in enumerate(concepts)
    )

    def on_complete() -> None:
        advance_to(PART_C_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Option")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_calibration()
