"""Part B-1 ratings route — the polished multi-section desirability survey.

Loads a :class:`QuestionnaireSpec` (via :mod:`survey_views.spec_source`), renders
the attributes selected by the respondent with a 1..5 rating per level, tracks
completion progress, and on submit assembles + validates a downloadable
``responses.csv`` using :mod:`conjoint.questionnaire`. The default flow renders
all active Part B-1 attributes; respondents can instead use a guided profile or
choose a custom subset, and skipped columns remain blank in the exported CSV.

Only the active Part B-1 attributes are shown; all rating/validation logic is
delegated to the tested core so this view stays thin.
"""

from __future__ import annotations

import streamlit as st

from conjoint import questionnaire as q
from conjoint.questionnaire import AttributeQuestion, QuestionnaireSpec
from survey_views.spec_source import load_spec
from survey_views.state import (
    ATTRIBUTE_SELECTION_KEY,
    GUIDED_PROFILE_KEY,
    QUESTION_FLOW_KEY,
    RESPONDENT_KEY,
    rating_key,
)

FLOW_ALL = "Full questionnaire"
FLOW_GUIDED = "Guided profile"
FLOW_CUSTOM = "Choose attributes"

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
    """Render the dynamic routing controls and return attributes to ask."""
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


def _collect_answers(
    spec: QuestionnaireSpec, attributes: tuple[AttributeQuestion, ...]
) -> dict[str, int | None]:
    """Render one section per active attribute; return ``{column: rating|None}``.

    Ratings start unselected (``index=None``) so progress is meaningful and the
    respondent makes an explicit choice rather than accepting a default.
    """
    scale = spec.scale
    options = list(range(int(scale.min), int(scale.max) + 1))
    answers: dict[str, int | None] = {}

    for position, attr in enumerate(attributes, start=1):
        with st.container(border=True):
            st.subheader(f"{position}. {attr.feature_name}")
            if attr.description:
                st.caption(attr.description)
            st.write(attr.prompt)
            st.caption(f"{scale.min} = least desirable · {scale.max} = most desirable")
            for level in attr.levels:
                column = q.response_column(attr.feature_name, level.code)
                answers[column] = st.radio(
                    f"**{level.label}**  (`{level.code}`)",
                    options=options,
                    index=None,
                    horizontal=True,
                    key=rating_key(column),
                )
    return answers


def _completed_attributes(
    attributes: tuple[AttributeQuestion, ...], answers: dict[str, int | None]
) -> int:
    """Count attributes whose every level has been rated."""
    completed = 0
    for attr in attributes:
        columns = [q.response_column(attr.feature_name, lv.code) for lv in attr.levels]
        if all(answers.get(col) is not None for col in columns):
            completed += 1
    return completed


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


def render_questionnaire() -> None:
    """Render the Part B-1 ratings page."""
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

    answers = _collect_answers(spec, selected_attributes)

    completed = _completed_attributes(selected_attributes, answers)
    total = len(selected_attributes)
    st.progress(
        completed / total, text=f"Progress: {completed}/{total} attributes rated"
    )

    if st.button("Build responses.csv", type="primary"):
        if completed < total:
            st.warning(
                f"{total - completed} attribute(s) not fully rated — those cells "
                "stay blank in the CSV."
            )
        _offer_download(spec, answers)


if __name__ == "__main__":  # pragma: no cover - manual ``streamlit run`` of the page
    render_questionnaire()
