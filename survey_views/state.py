"""Shared ``st.session_state`` keys for the survey app.

Centralising the keys keeps the intro page, the ratings page, the
``survey.py`` router and the ACBC stages (BYO / Screener / Tournament) in
agreement about where the respondent id, the per-level rating widgets and
the sequential step pointer live in session state.
"""

from __future__ import annotations

#: The respondent id entered on the intro page and reused when building
#: ``responses.csv`` on the ratings page.
RESPONDENT_KEY = "survey_respondent_id"

#: The ratings :class:`st.Page`, stashed by the router so the intro page's
#: "Start" button can :func:`st.switch_page` to it.
QUESTIONNAIRE_PAGE_KEY = "survey_questionnaire_page"

#: The respondent's questionnaire routing choice on the ratings page.
QUESTION_FLOW_KEY = "survey_question_flow"

#: The selected attribute names when the respondent chooses a custom subset.
ATTRIBUTE_SELECTION_KEY = "survey_attribute_selection"

#: The guided profile selected when the respondent wants a shorter focused flow.
GUIDED_PROFILE_KEY = "survey_guided_profile"

#: Active sequential stage identifier (``ratings`` / ``acbc_byo`` /
#: ``acbc_screener`` / ``acbc_tournament``). Changing the active stage resets
#: :data:`STEP_INDEX_KEY` to ``0`` so the new flow starts at its first step.
STAGE_KEY = "survey_stage"

#: Cursor inside the active stage's step sequence — incremented by Next and
#: decremented by Back in :func:`survey_views.navigation.render_sequence`.
STEP_INDEX_KEY = "survey_stage_step_index"

#: Two-level dict ``{stage: {step_identifier: value}}`` holding every
#: respondent answer collected across stages. Stage-scoped to avoid name
#: collisions across flows (e.g. the same attribute key used in BYO and
#: ratings should not overwrite each other).
STAGE_ANSWERS_KEY = "survey_stage_answers"

#: Survey "mode" — ``rating`` (legacy OLS path) or ``acbc`` (BYO + Screener
#: + Tournament). Picked on the intro page; consumed by the router's
#: ``flow_pages`` gate. This is a **plain** (non-widget) key on purpose: the
#: intro radio writes its choice here via a callback so the mode survives the
#: ``st.switch_page`` rerun, during which the intro page (and its radio widget)
#: is not rendered and Streamlit would garbage-collect a widget-keyed value.
SURVEY_MODE_KEY = "survey_mode"

#: Widget key for the intro mode radio. Kept distinct from
#: :data:`SURVEY_MODE_KEY` so the router never reads a value that vanishes when
#: the radio stops rendering (see the note above).
SURVEY_MODE_CHOICE_KEY = "survey_mode_choice"

#: ACBC ``st.Page`` references stashed by the router for cross-page nav.
ACBC_BYO_PAGE_KEY = "survey_acbc_byo_page"
ACBC_SCREENER_PAGE_KEY = "survey_acbc_screener_page"
ACBC_TOURNAMENT_PAGE_KEY = "survey_acbc_tournament_page"
ACBC_SUMMARY_PAGE_KEY = "survey_acbc_summary_page"


def rating_key(column: str) -> str:
    """Session-state / widget key for one ``{attribute}__{level_code}`` rating."""
    return f"survey_rating__{column}"
