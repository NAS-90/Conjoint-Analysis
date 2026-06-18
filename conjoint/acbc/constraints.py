"""B1 → B2 → B4 bridge: derive an anchor and apply hard constraints.

In the linear questionnaire there is no Build-Your-Own step; the B4 pair
comparison concepts are generated "from the B1/B2 answers" instead. This module is
the pure (Streamlit-free) glue:

* :func:`anchor_from_ratings` — turn the B1 desirability ratings into the
  respondent's ideal :class:`~conjoint.acbc.design.Profile`, honouring the B2
  must-have / unacceptable level constraints.
* :func:`filter_by_constraints` — drop generated profiles that violate the B2
  constraints (carry an unacceptable level, or miss a must-have level).
* :func:`split_constraints` — fold the per-level B2 verdicts collected by the
  UI into ``(must_have, unacceptable)`` maps the two functions above consume.

All functions return new objects and never mutate their inputs.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from conjoint.acbc.design import Profile
from conjoint.questionnaire import QuestionnaireSpec

#: ``{attribute: required_level_code}`` — at most one required level per attribute.
MustHave = Mapping[str, str]
#: ``{attribute: {excluded_level_code, ...}}``.
Unacceptable = Mapping[str, "set[str] | frozenset[str] | Sequence[str]"]
#: ``{attribute: {level_code: rating}}`` as collected by the B1 ratings stage.
Ratings = Mapping[str, Mapping[str, int]]

#: B2 verdict labels stored per (attribute, level).
VERDICT_MUST_HAVE = "must_have"
VERDICT_UNACCEPTABLE = "unacceptable"
VERDICT_FINE = "fine"


def _normalise_unacceptable(
    unacceptable: Unacceptable | None,
) -> dict[str, set[str]]:
    """Copy ``unacceptable`` into ``{attribute: set(levels)}`` (never mutated)."""
    return {attr: set(levels) for attr, levels in (unacceptable or {}).items()}


def _best_level(
    codes: Sequence[str],
    level_ratings: Mapping[str, int],
    excluded: set[str],
) -> str:
    """Highest-rated acceptable level; ties resolve to spec order.

    Falls back to the full level list when *every* level is excluded (a
    contradictory B2 answer) so the anchor always has a value, and to the
    first acceptable level when no ratings were given for the attribute.
    """
    acceptable = [code for code in codes if code not in excluded]
    pool = acceptable or list(codes)
    best = pool[0]
    best_rating = level_ratings.get(best)
    for code in pool[1:]:
        rating = level_ratings.get(code)
        if rating is None:
            continue
        if best_rating is None or rating > best_rating:
            best, best_rating = code, rating
    return best


def anchor_from_ratings(
    ratings: Ratings,
    spec: QuestionnaireSpec,
    *,
    must_have: MustHave | None = None,
    unacceptable: Unacceptable | None = None,
) -> Profile:
    """Derive the respondent's ideal :class:`Profile` from B1 + B2.

    For each active attribute the chosen level is, in priority order:

    1. the B2 must-have level (if the respondent marked one), else
    2. the highest-rated level that is not B2-unacceptable, else
    3. the first acceptable level in spec order (no ratings yet).
    """
    forced = dict(must_have or {})
    excluded = _normalise_unacceptable(unacceptable)

    pairs: list[tuple[str, str]] = []
    for attr in spec.active_attributes:
        name = attr.feature_name
        codes = [level.code for level in attr.levels]
        required = forced.get(name)
        if required is not None and required in codes:
            chosen = required
        else:
            chosen = _best_level(codes, ratings.get(name, {}) or {}, excluded.get(name, set()))
        pairs.append((name, chosen))
    return Profile(levels=tuple(pairs))


def filter_by_constraints(
    profiles: Sequence[Profile],
    *,
    must_have: MustHave | None = None,
    unacceptable: Unacceptable | None = None,
) -> tuple[Profile, ...]:
    """Keep only profiles that satisfy the B2 hard constraints.

    A profile is dropped when it carries an unacceptable level, or when it
    differs from a must-have level the respondent required for that attribute.
    """
    forced = dict(must_have or {})
    excluded = _normalise_unacceptable(unacceptable)

    kept: list[Profile] = []
    for profile in profiles:
        ok = True
        for attribute, code in profile.levels:
            if code in excluded.get(attribute, set()):
                ok = False
                break
            required = forced.get(attribute)
            if required is not None and code != required:
                ok = False
                break
        if ok:
            kept.append(profile)
    return tuple(kept)


def split_constraints(
    verdicts: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Fold per-level B2 verdicts into ``(must_have, unacceptable)`` maps.

    ``verdicts`` is ``{attribute: {level_code: verdict}}`` where verdict is one
    of :data:`VERDICT_MUST_HAVE` / :data:`VERDICT_UNACCEPTABLE` /
    :data:`VERDICT_FINE`. Only the **first** must-have level per attribute is
    kept (a single attribute cannot require two different levels).
    """
    must_have: dict[str, str] = {}
    unacceptable: dict[str, set[str]] = {}
    for attribute, level_verdicts in verdicts.items():
        for level, verdict in level_verdicts.items():
            if verdict == VERDICT_UNACCEPTABLE:
                unacceptable.setdefault(attribute, set()).add(level)
            elif verdict == VERDICT_MUST_HAVE and attribute not in must_have:
                must_have[attribute] = level
    return must_have, unacceptable
