"""ACBC Screener stage — Yes/No on BYO-anchored profile pool.

After BYO (:mod:`conjoint.acbc.byo`) the respondent sees a small pool
of profiles that *differ from the BYO anchor by a few levels at a time*
— would they "consider" each one? Profiles the respondent flags as
unacceptable are removed before the Tournament; profiles they accept
become Tournament candidates.

Public surface:

* :func:`seed_screener_pool` — generate the Screener profile pool by
  perturbing the BYO anchor on 1..``max_changes`` randomly-chosen
  attributes. Each profile is guaranteed to differ from the anchor in
  at least one attribute (otherwise the Yes/No is meaningless).
* :func:`filter_survivors` — given Screener responses, drop profiles
  that look "unacceptable" (Yes/No = 0) more aggressively than the
  configurable threshold.

The UI consumes these via :mod:`survey_views.acbc_screener`.
"""

from __future__ import annotations

import random
from collections import OrderedDict
from typing import Iterable, Sequence

from conjoint.acbc.design import Profile
from conjoint.acbc.responses import ScreenerResponse

#: Default number of Screener profiles shown when no override is supplied.
DEFAULT_SCREENER_POOL = 12
#: Default cap on how many attributes can differ from the anchor per profile.
DEFAULT_MAX_CHANGES = 3


def _anchor_dict(anchor: Profile) -> "OrderedDict[str, str]":
    """``OrderedDict({attribute: code, ...})`` view of the BYO anchor."""
    return OrderedDict(anchor.levels)


def seed_screener_pool(
    anchor: Profile,
    attribute_levels: "OrderedDict[str, Sequence[str]] | dict[str, Sequence[str]]",
    *,
    n_profiles: int = DEFAULT_SCREENER_POOL,
    max_changes: int = DEFAULT_MAX_CHANGES,
    seed: int | None = None,
) -> tuple[Profile, ...]:
    """Build the Screener profile pool centred on ``anchor``.

    Each profile starts as a copy of the anchor, then 1..``max_changes``
    distinct attributes are flipped to a *different* level (so the
    profile is provably distinct from the anchor). The pool is
    deterministic in ``seed``.

    Raises ``ValueError`` if no attribute has more than one level (so a
    perturbation is impossible).
    """
    if n_profiles <= 0:
        raise ValueError(f"n_profiles must be positive (got {n_profiles})")
    if max_changes <= 0:
        raise ValueError(f"max_changes must be positive (got {max_changes})")

    anchor_map = _anchor_dict(anchor)
    multi_level = [
        attribute for attribute, levels in attribute_levels.items() if len(levels) > 1
    ]
    if not multi_level:
        raise ValueError("at least one attribute must have >1 level to seed the Screener")

    rng = random.Random(seed)
    profiles: list[Profile] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    attempts = 0
    target_changes = min(max_changes, len(multi_level))

    while len(profiles) < n_profiles and attempts < n_profiles * 20:
        attempts += 1
        changes = rng.randint(1, target_changes)
        attrs_to_change = rng.sample(multi_level, changes)
        candidate = OrderedDict(anchor_map)
        for attribute in attrs_to_change:
            current = candidate[attribute]
            alternatives = [
                code for code in attribute_levels[attribute] if code != current
            ]
            candidate[attribute] = rng.choice(alternatives)
        key = tuple(candidate.items())
        if key in seen:
            continue
        seen.add(key)
        profiles.append(Profile(levels=key))
    return tuple(profiles)


def screener_response_record(
    respondent: object,
    task_id: int,
    profile: Profile,
    *,
    accepted: bool,
) -> ScreenerResponse:
    """Convenience constructor for :class:`ScreenerResponse`."""
    return ScreenerResponse(
        respondent=respondent, task_id=task_id, profile=profile, accepted=bool(accepted)
    )


def filter_survivors(
    responses: Iterable[ScreenerResponse],
    *,
    threshold: int = 1,
) -> tuple[Profile, ...]:
    """Return profiles the respondent flagged ``accepted=True``.

    ``threshold`` is a vestigial knob — the documented ACBC convention
    keeps every "Yes" profile and drops every "No". We keep the
    parameter so future code can require ``threshold`` Yes votes when
    multiple respondents share a pool.
    """
    yes_counts: dict[tuple[tuple[str, str], ...], int] = {}
    profile_lookup: dict[tuple[tuple[str, str], ...], Profile] = {}
    for response in responses:
        key = tuple(response.profile.levels)
        profile_lookup.setdefault(key, response.profile)
        yes_counts[key] = yes_counts.get(key, 0) + (1 if response.accepted else 0)

    survivors = [profile for key, profile in profile_lookup.items() if yes_counts[key] >= threshold]
    return tuple(survivors)


def unacceptable_levels(
    responses: Iterable[ScreenerResponse],
    *,
    min_rejections: int = 2,
) -> dict[str, set[str]]:
    """Heuristic: levels present in ``min_rejections`` rejected profiles.

    ACBC literature uses this signal to detect *must-have / must-avoid*
    levels — if the respondent consistently rejects every profile that
    carries level ``L_a`` of attribute ``a``, ``L_a`` is "unacceptable"
    and can be excluded from the Tournament.
    """
    rejection_counts: dict[tuple[str, str], int] = {}
    for response in responses:
        if response.accepted:
            continue
        for attribute, code in response.profile.levels:
            key = (attribute, code)
            rejection_counts[key] = rejection_counts.get(key, 0) + 1

    flagged: dict[str, set[str]] = {}
    for (attribute, code), count in rejection_counts.items():
        if count >= min_rejections:
            flagged.setdefault(attribute, set()).add(code)
    return flagged
