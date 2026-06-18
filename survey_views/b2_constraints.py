"""B2 — must-have / unacceptable feature levels (ACBC screening logic).

ACBC's core idea is to learn a respondent's hard constraints first, then only
ever show them realistic concepts. This section asks, per attribute, whether any
level is an absolute **must-have** or one they would **never accept** (e.g. "must
have iOS", "won't accept 64 GB"). Both are optional — most attributes have no
rule.

On Finish this section:

1. folds the per-level answers into ``must_have`` / ``unacceptable`` maps
   (:func:`conjoint.acbc.constraints.split_constraints`) and persists them for
   B4 / B5,
2. derives the respondent's ideal **anchor** from the spec's level order,
   honouring those constraints
   (:func:`conjoint.acbc.constraints.anchor_from_ratings`, called with no
   ratings), and
3. advances to B4 (pair comparison).

Answers are recorded into the responses CSV by the summary page (stage
``musthave``).
"""

from __future__ import annotations

import streamlit as st

from conjoint.acbc.constraints import (
    VERDICT_MUST_HAVE,
    VERDICT_UNACCEPTABLE,
    anchor_from_ratings,
    split_constraints,
)
from survey_views.navigation import (
    Step,
    advance_to,
    get_answer,
    record_answer,
    render_sequence,
    stage_answers,
)
from survey_views.spec_source import (
    attribute_display_name,
    format_level,
    level_label_map,
    load_spec,
)
from survey_views.state import (
    ACBC_ANCHOR_KEY,
    ACBC_TOURNAMENT_PAGE_KEY,
    MUST_HAVE_KEY,
    UNACCEPTABLE_KEY,
)
from survey_views.theme import apply_base_theme, flow_header

#: Stage identifier under which B2 per-attribute constraints are stored.
STAGE = "musthave"


def _attribute_constraint_step(attr, labels: dict[str, dict[str, str]]) -> Step:
    """One :class:`Step` collecting must-have / unacceptable rules for one attribute."""
    name = attr.feature_name
    codes = [level.code for level in attr.levels]

    def render() -> bool:
        if attr.description:
            st.caption(attr.description)
        st.write(
            "Most people are fine with any option here — only set a rule if you "
            "feel strongly."
        )
        prior = get_answer(STAGE, name, default={}) or {}
        prior_mh = prior.get("must_have") if isinstance(prior, dict) else None

        mh_options = [None, *codes]
        mh_index = mh_options.index(prior_mh) if prior_mh in mh_options else 0
        must = st.selectbox(
            "Must have (optional)",
            options=mh_options,
            index=mh_index,
            format_func=lambda c: "No preference"
            if c is None
            else format_level(labels, name, c),
            key=f"musthave__mh__{name}",
        )
        prior_un = [
            c
            for c in (prior.get("unacceptable") or [])
            if isinstance(prior, dict) and c in codes
        ]
        never = st.multiselect(
            "Would never accept (optional)",
            options=codes,
            default=prior_un,
            format_func=lambda c: format_level(labels, name, c),
            key=f"musthave__un__{name}",
        )
        if must is not None and must in never:
            st.caption(
                "You marked the same option as both must-have and never — we'll "
                "treat it as a must-have."
            )
        record_answer(STAGE, name, {"must_have": must, "unacceptable": list(never)})
        return True  # constraints are optional, so the page is always complete

    return Step(identifier=name, title=attribute_display_name(name), render=render)


def _persist_constraints_and_anchor() -> None:
    """Fold answers into constraint maps, derive the anchor, stash everything."""
    spec = load_spec()
    if spec is None:
        return
    answers = stage_answers(STAGE)
    verdicts: dict[str, dict[str, str]] = {}
    for attribute, value in answers.items():
        if not isinstance(value, dict):
            continue
        per_level: dict[str, str] = {}
        must = value.get("must_have")
        if must:
            per_level[must] = VERDICT_MUST_HAVE
        for code in value.get("unacceptable") or []:
            if code != must:
                per_level[code] = VERDICT_UNACCEPTABLE
        if per_level:
            verdicts[attribute] = per_level

    must_have, unacceptable = split_constraints(verdicts)
    st.session_state[MUST_HAVE_KEY] = must_have
    st.session_state[UNACCEPTABLE_KEY] = {a: set(s) for a, s in unacceptable.items()}

    # There is no B1 rating step any more, so the anchor falls back to the spec's
    # level order, with any B2 must-have overriding it per attribute.
    anchor = anchor_from_ratings(
        {}, spec, must_have=must_have, unacceptable=unacceptable
    )
    st.session_state[ACBC_ANCHOR_KEY] = anchor


def render_constraints() -> None:
    """Render B2 (one attribute per screen)."""
    apply_base_theme()
    spec = load_spec()
    if spec is None:
        return
    active = spec.active_attributes
    if not active:
        st.warning("There are no features to set rules for right now.")
        return

    flow_header(
        3,
        6,
        "Any deal-breakers?",
        "Tell us if any feature is an absolute must — or something you'd never accept.",
    )

    labels = level_label_map(spec)
    steps = tuple(_attribute_constraint_step(attr, labels) for attr in active)

    def on_complete() -> None:
        _persist_constraints_and_anchor()
        advance_to(ACBC_TOURNAMENT_PAGE_KEY)

    render_sequence(STAGE, steps, on_complete=on_complete, progress_label="Feature")


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run``
    render_constraints()
