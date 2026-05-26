"""ACBC Build-Your-Own (BYO) stage.

The BYO is the first ACBC stage: the respondent picks their most
preferred level for **each attribute** independently. The answers seed
the Screener pool (see :mod:`conjoint.acbc.screener`) and feed the MNL
likelihood as soft constraints in later phases.

This module is pure data + helpers — the UI lives in
:mod:`survey_views.acbc_byo`. Public surface:

* :func:`byo_questions` — render-ready list of attribute/levels pairs
  drawn from a :class:`QuestionnaireSpec`.
* :func:`byo_to_anchor` — turn collected answers into a ``Profile`` the
  Screener uses as its seed (the "ideal" configuration).
* :func:`byo_to_responses` — long-format BYO rows for
  :func:`conjoint.acbc.responses.assemble_byo_responses`.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Mapping, Sequence

from conjoint.acbc.design import Profile
from conjoint.acbc.responses import ByoResponse
from conjoint.questionnaire import QuestionnaireSpec


@dataclass(frozen=True)
class ByoQuestion:
    """One BYO question: pick a preferred level for ``attribute``."""

    attribute: str
    description: str
    prompt: str
    levels: tuple[tuple[str, str], ...]  # ((code, label), ...)


def byo_questions(spec: QuestionnaireSpec) -> tuple[ByoQuestion, ...]:
    """Build one BYO question per **active** Part B-1 attribute."""
    questions: list[ByoQuestion] = []
    for attribute in spec.active_attributes:
        levels = tuple((level.code, level.label) for level in attribute.levels)
        questions.append(
            ByoQuestion(
                attribute=attribute.feature_name,
                description=attribute.description,
                prompt=f"Which {attribute.feature_name} would you most prefer?",
                levels=levels,
            )
        )
    return tuple(questions)


def byo_to_anchor(
    answers: Mapping[str, str],
    spec: QuestionnaireSpec,
) -> Profile:
    """Turn BYO answers into the anchor :class:`Profile`.

    Active attributes missing from ``answers`` default to the **first**
    level of that attribute (a documented choice — the Screener then
    perturbs the anchor anyway).
    """
    pairs: list[tuple[str, str]] = []
    for attribute in spec.active_attributes:
        chosen = answers.get(attribute.feature_name)
        valid_codes = {level.code for level in attribute.levels}
        if chosen is None or chosen not in valid_codes:
            chosen = attribute.levels[0].code
        pairs.append((attribute.feature_name, chosen))
    return Profile(levels=tuple(pairs))


def byo_to_responses(
    answers: Mapping[str, str],
    respondent: object,
    *,
    spec: QuestionnaireSpec | None = None,
    attribute_order: Sequence[str] | None = None,
) -> tuple[ByoResponse, ...]:
    """Long-format BYO records for :func:`assemble_byo_responses`.

    ``attribute_order`` lets the caller override the iteration order
    when no spec is supplied. When neither is given, the order of
    ``answers`` is used.
    """
    if spec is not None:
        order: Sequence[str] = [attr.feature_name for attr in spec.active_attributes]
    elif attribute_order is not None:
        order = list(attribute_order)
    else:
        order = list(answers.keys())

    records: list[ByoResponse] = []
    for index, attribute in enumerate(order, start=1):
        chosen = answers.get(attribute)
        if chosen is None:
            continue
        records.append(
            ByoResponse(
                respondent=respondent,
                task_id=index,
                attribute=attribute,
                chosen_level=str(chosen),
            )
        )
    return tuple(records)


def anchor_to_dict(anchor: Profile) -> "OrderedDict[str, str]":
    """``OrderedDict({attribute: code, ...})`` view of the BYO anchor."""
    return OrderedDict(anchor.levels)
