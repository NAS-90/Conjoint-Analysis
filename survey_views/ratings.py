"""Part B-1 ratings route — single-page-per-attribute desirability survey.

Loads a :class:`QuestionnaireSpec` (via :mod:`survey_views.spec_source`),
renders one attribute per page through
:func:`survey_views.navigation.render_sequence`, tracks completion via the
shared step counter, and on Finish assembles + validates a downloadable
``responses.csv`` using :mod:`conjoint.questionnaire`. Respondents can still
opt into the Full / Guided profile / Custom subset flows from the intro of
the page; the choice scopes the visible attribute list before the
sequential controller takes over.

Only the active Part B-1 attributes are shown; all rating/validation logic
is delegated to the tested core so this view stays thin.
"""

from __future__ import annotations

import streamlit as st

from conjoint import questionnaire as q
from conjoint.questionnaire import AttributeQuestion, QuestionnaireSpec
from survey_views.navigation import (
    Step,
    get_answer,
    record_answer,
    render_sequence,
    reset_stage,
    stage_answers,
)
from survey_views.spec_source import load_spec
from survey_views.state import (
    ATTRIBUTE_SELECTION_KEY,
    GUIDED_PROFILE_KEY,
    QUESTION_FLOW_KEY,
    RESPONDENT_KEY,
)

FLOW_ALL = "Full questionnaire"
FLOW_GUIDED = "Guided profile"
FLOW_CUSTOM = "Choose attributes"

#: Stage identifier under which per-attribute answers are stored
#: (``stage_answers("ratings")[attribute_name] = {level_code: rating}``).
STAGE = "ratings"

GUIDED_PROFILES: dict[str, tuple[str, ...]] = {
    "Performance": (
        "engine",
        "injection",
        "transmission",
        "gears",
        "power",
        "processor",
        "speed",
    ),
    "Ease of use": (
        "transmission",
        "shuttle",
        "steering",
        "control",
        "interface",
        "software",
    ),
    "Comfort and quality": (
        "cabin",
        "seat",
        "screen",
        "display",
        "camera",
        "quality",
    ),
    "Range and endurance": (
        "tank",
        "battery",
        "range",
        "fuel",
        "capacity",
        "runtime",
    ),
}


# ---------------------------------------------------------------------------
# Attribute selection (Full / Guided / Custom)
# ---------------------------------------------------------------------------
def _matches_profile(attr: AttributeQuestion, keywords: tuple[str, ...]) -> bool:
    """Return whether an attribute appears relevant to a guided profile."""
    haystack = " ".join(
        [
            attr.feature_name,
            attr.description,
            attr.prompt,
            " ".join(level.label for level in attr.levels),
        ]
    ).casefold()
    return any(keyword.casefold() in haystack for keyword in keywords)


def _select_attributes(
    active: tuple[AttributeQuestion, ...],
) -> tuple[tuple[AttributeQuestion, ...], str]:
    """Render the routing controls and return the attributes to ask."""
    names = [attr.feature_name for attr in active]
    by_name = {attr.feature_name: attr for attr in active}

    flow = st.selectbox(
        "Questionnaire flow",
        options=[FLOW_ALL, FLOW_GUIDED, FLOW_CUSTOM],
        index=0,
        key=QUESTION_FLOW_KEY,
        help=(
            "Use all attributes, use a guided profile, or choose the exact "
            "attributes this respondent should rate."
        ),
    )

    if flow == FLOW_CUSTOM:
        selected_names = st.multiselect(
            "Attributes to include",
            options=names,
            default=names,
            key=ATTRIBUTE_SELECTION_KEY,
            help="Questions for unselected attributes are skipped and exported as blanks.",
        )
        selected = tuple(by_name[name] for name in selected_names)
        return selected, FLOW_CUSTOM

    if flow == FLOW_GUIDED:
        profile = st.radio(
            "Respondent priority",
            options=list(GUIDED_PROFILES),
            horizontal=True,
            key=GUIDED_PROFILE_KEY,
        )
        keywords = GUIDED_PROFILES[profile]
        selected = tuple(attr for attr in active if _matches_profile(attr, keywords))
        if not selected:
            st.info(
                "No exact matches for this profile in the current spec, so the "
                "full questionnaire is shown."
            )
            return active, f"{FLOW_GUIDED}: {profile}"
        return selected, f"{FLOW_GUIDED}: {profile}"

    return active, FLOW_ALL


# ---------------------------------------------------------------------------
# Single-attribute step renderer
# ---------------------------------------------------------------------------
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
                f"**{level.label}**  (`{level.code}`)",
                options=options,
                index=default_index,
                horizontal=True,
                key=f"survey_rating__{attr.feature_name}__{level.code}",
            )
            if value is not None:
                ratings[level.code] = int(value)

        record_answer(STAGE, attr.feature_name, ratings)
        return len(ratings) == len(attr.levels)

    return Step(identifier=attr.feature_name, title=attr.feature_name, render=render)


# ---------------------------------------------------------------------------
# Finish: assemble + validate + download
# ---------------------------------------------------------------------------
def _flat_answers(
    spec: QuestionnaireSpec, attributes: tuple[AttributeQuestion, ...]
) -> dict[str, int | None]:
    """Flatten ``stage_answers("ratings")`` into the column form."""
    per_attr = stage_answers(STAGE)
    flat: dict[str, int | None] = {}
    for attr in spec.active_attributes:
        ratings = per_attr.get(attr.feature_name, {}) or {}
        in_scope = attr in attributes
        for level in attr.levels:
            column = q.response_column(attr.feature_name, level.code)
            value = ratings.get(level.code) if in_scope else None
            flat[column] = value
    return flat


def _offer_download(spec: QuestionnaireSpec, answers: dict[str, int | None]) -> None:
    """Validate the assembled answers and, if valid, offer ``responses.csv``."""
    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"
    frame = q.responses_from_answers([answers], spec, respondent_ids=[respondent])
    problems = q.validate_responses(frame, spec)
    if problems:
        st.error("Response validation failed:")
        for problem in problems:
            st.write(f"- {problem}")
        return
    st.success(
        "Responses look valid. Download below and feed to "
        "`python -m conjoint.estimate`."
    )
    st.dataframe(frame, width="stretch")
    st.download_button(
        "Download responses.csv",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name="responses.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _completed_attributes(attributes: tuple[AttributeQuestion, ...]) -> int:
    """Count attributes whose every level has been rated in stage state."""
    per_attr = stage_answers(STAGE)
    completed = 0
    for attr in attributes:
        ratings = per_attr.get(attr.feature_name, {}) or {}
        if all(level.code in ratings for level in attr.levels):
            completed += 1
    return completed


def render_questionnaire() -> None:
    """Render the Part B-1 ratings page (single attribute per page)."""
    st.title("Part B-1 — desirability ratings")

    spec = load_spec()
    if spec is None:
        return

    active = spec.active_attributes
    if not active:
        st.warning("This spec has no active Part B-1 rating attributes.")
        return

    selected_attributes, flow_label = _select_attributes(active)
    if not selected_attributes:
        st.warning("Choose at least one attribute to render questions.")
        return

    respondent = str(st.session_state.get(RESPONDENT_KEY, "") or "").strip() or "1"
    st.caption(
        f"Respondent **{respondent}** · {flow_label} · "
        f"{len(selected_attributes)}/{len(active)} attribute(s) shown · rating scale "
        f"{spec.scale.min}–{spec.scale.max} (higher = more desirable)."
    )
    skipped = len(active) - len(selected_attributes)
    if skipped:
        st.info(
            f"{skipped} attribute(s) are skipped for this flow; their response "
            "columns stay blank in the downloaded CSV."
        )

    steps = tuple(_attribute_step(spec, attr) for attr in selected_attributes)

    completed_state = st.session_state.setdefault("survey_ratings_finished", False)
    finished_flag = bool(completed_state)

    def on_complete() -> None:
        st.session_state["survey_ratings_finished"] = True

    if not finished_flag:
        render_sequence(
            STAGE,
            steps,
            on_complete=on_complete,
            progress_label="Attribute",
        )

    if st.session_state.get("survey_ratings_finished"):
        completed = _completed_attributes(selected_attributes)
        total = len(selected_attributes)
        if completed < total:
            st.warning(
                f"{total - completed} attribute(s) not fully rated — those cells "
                "stay blank in the CSV."
            )
        _offer_download(spec, _flat_answers(spec, selected_attributes))
        if st.button("Restart questionnaire"):
            st.session_state["survey_ratings_finished"] = False
            reset_stage(STAGE)
            st.rerun()


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run`` of the page
    render_questionnaire()
