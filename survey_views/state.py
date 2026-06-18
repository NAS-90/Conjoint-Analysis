"""Shared ``st.session_state`` keys for the survey app.

Centralising the keys keeps the intro page, the section views, the
``survey.py`` router and the ACBC stages (BYO / Screener / Tournament) in
agreement about where the respondent id, the per-section answers and
the sequential step pointer live in session state.
"""

from __future__ import annotations

#: The respondent id entered on the intro page and reused when building
#: ``responses.csv`` on the final "Thank you" page.
RESPONDENT_KEY = "survey_respondent_id"

#: Active sequential stage identifier (``background`` /
#: ``musthave`` / ``acbc_tournament`` / ``calibration`` / ``wtp``). Changing the
#: active stage resets :data:`STEP_INDEX_KEY` to ``0`` so the new section starts
#: at its first step. Read another stage's answers with
#: :func:`survey_views.navigation.peek_stage` (no reset) — never ``stage_answers``.
STAGE_KEY = "survey_stage"

#: Cursor inside the active stage's step sequence — incremented by Next and
#: decremented by Back in :func:`survey_views.navigation.render_sequence`.
STEP_INDEX_KEY = "survey_stage_step_index"

#: Two-level dict ``{stage: {step_identifier: value}}`` holding every
#: respondent answer collected across stages. Stage-scoped to avoid name
#: collisions across flows (e.g. the same attribute key used in BYO and
#: ratings should not overwrite each other).
STAGE_ANSWERS_KEY = "survey_stage_answers"

#: ACBC ``st.Page`` references stashed by the router for cross-page nav.
ACBC_BYO_PAGE_KEY = "survey_acbc_byo_page"
ACBC_SCREENER_PAGE_KEY = "survey_acbc_screener_page"
ACBC_TOURNAMENT_PAGE_KEY = "survey_acbc_tournament_page"
ACBC_SUMMARY_PAGE_KEY = "survey_acbc_summary_page"

#: Linear-flow ``st.Page`` references stashed by the router so each section's
#: "Next/Finish" can :func:`st.switch_page` to the following section. B4 reuses
#: :data:`ACBC_TOURNAMENT_PAGE_KEY`, and the final page reuses
#: :data:`ACBC_SUMMARY_PAGE_KEY`.
PART_A_PAGE_KEY = "survey_part_a_page"
B0_PAGE_KEY = "survey_b0_page"
B2_PAGE_KEY = "survey_b2_page"
B5_PAGE_KEY = "survey_b5_page"
PART_C_PAGE_KEY = "survey_part_c_page"

#: The respondent's ideal :class:`~conjoint.acbc.design.Profile`, derived in B2
#: from the spec's level order honouring the B2 constraints
#: (:func:`conjoint.acbc.constraints.anchor_from_ratings`, called with no
#: ratings). Consumed by B4 (pool generation) and B5 (calibration concepts). The
#: value string is unchanged from the legacy BYO key so session continuity holds.
ACBC_ANCHOR_KEY = "acbc_anchor"

#: B2 hard constraints persisted for B4/B5: ``{attribute: required_level}`` and
#: ``{attribute: {excluded_level, ...}}``.
MUST_HAVE_KEY = "survey_must_have"
UNACCEPTABLE_KEY = "survey_unacceptable"


def rating_key(column: str) -> str:
    """Session-state / widget key for one ``{attribute}__{level_code}`` rating."""
    return f"survey_rating__{column}"
