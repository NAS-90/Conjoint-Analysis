"""Shared ``st.session_state`` keys for the survey app.

Centralising the keys keeps the intro page, the ratings page and the
``survey.py`` router in agreement about where the respondent id and the
per-level rating widgets live in session state.
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


def rating_key(column: str) -> str:
    """Session-state / widget key for one ``{attribute}__{level_code}`` rating."""
    return f"survey_rating__{column}"
