"""Synthetic *multi-respondent* survey simulation (full Part A/B/C walk).

:mod:`conjoint.acbc.synthetic` draws Tournament-only choices for the quality
demo. This module goes one level up: it simulates a whole **population** of
heterogeneous respondents walking the *entire* linear questionnaire — Part A
background, B2 deal-breakers, B4 pair comparisons, B5 calibration and Part C
WTP — and assembles each with the production :mod:`conjoint.acbc.responses`
code. The output is exactly the long-format ``acbc_responses.csv`` a real
fielded study would yield, only with *known* ground truth.

Why utility-driven choices matter
----------------------------------
Each respondent gets a **true part-worth vector** drawn from a population mean
plus heterogeneity. Tournament choices are a Gumbel-argmax over the
alternatives' systematic utilities — an MNL realisation — so feeding the result
to :func:`conjoint.acbc.estimate.fit_hb` *recovers* the planted structure. The
true β is laid out in the exact effects-coded column order the estimator uses
(``{attr}__{code}`` for ``levels[:-1]`` in spec order — see
:func:`conjoint.acbc.design.effects_code`), which is what makes recovery exact.

Layering
--------
This module is part of the Streamlit-free ``conjoint`` package, so it never
imports ``survey_views`` or ``streamlit``. The survey "banks" (Part A questions,
Part C features, amount bands) are **injected** as parameters by the thin
``scripts``/``dashboard`` callers; only their duck-typed attributes are used
(see :class:`BackgroundQuestion` / :class:`WtpFeature`).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

import numpy as np
import pandas as pd

from conjoint.acbc import responses as R
from conjoint.acbc.constraints import anchor_from_ratings, filter_by_constraints
from conjoint.acbc.design import (
    Profile,
    attribute_levels_from_spec,
    effects_code,
    generate_profiles,
)
from conjoint.acbc.estimate import beta_to_level_utilities
from conjoint.acbc.screener import seed_screener_pool
from conjoint.acbc.tournament import Task, build_tasks
from conjoint.questionnaire import QuestionnaireSpec


# ---------------------------------------------------------------------------
# Injected survey banks (duck-typed — see survey_views.section_source)
# ---------------------------------------------------------------------------
class BackgroundQuestion(Protocol):
    """A Part A profiling question (structurally ``section_source.ProfileQuestion``)."""

    identifier: str
    options: Sequence[str]
    multi: bool


class WtpFeature(Protocol):
    """A Part C upgrade (structurally ``section_source.WtpFeature``)."""

    identifier: str
    label: str


#: Part C feature id → modelled attribute, when they are not spelled identically.
_WTP_FEATURE_ALIASES: dict[str, str] = {"memory": "ram", "storage_upgrade": "storage"}


def default_wtp_feature_attribute(
    wtp_features: Sequence[WtpFeature],
    attribute_levels: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    """Map each Part C feature to a modelled attribute where one obviously exists.

    A feature whose id is itself an attribute name maps to it; a few known
    aliases (``memory`` → ``ram``) are folded in. Features with no clear
    attribute (e.g. ``connectivity``) are simply omitted — the WTP draw then
    falls back to a neutral band, never raising.
    """
    mapping: dict[str, str] = {}
    for feature in wtp_features:
        identifier = feature.identifier
        if identifier in attribute_levels:
            mapping[identifier] = identifier
        elif _WTP_FEATURE_ALIASES.get(identifier) in attribute_levels:
            mapping[identifier] = _WTP_FEATURE_ALIASES[identifier]
    return mapping


# ---------------------------------------------------------------------------
# Ground-truth dataclasses
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PopulationModel:
    """The planted population — shared by every simulated respondent."""

    attribute_levels: "OrderedDict[str, tuple[str, ...]]"
    column_names: tuple[str, ...]
    mean_beta: np.ndarray  # (n_features,) effects-coded population mean
    hetero_sd: np.ndarray  # (n_features,) per-feature heterogeneity SD (diag Σ)
    part_worth_ranges: "OrderedDict[str, float]"  # planted best-worst spread per attr
    mean_part_worths: "OrderedDict[str, OrderedDict[str, float]]"  # full per-level utilities


@dataclass(frozen=True)
class RespondentTruth:
    """One respondent's drawn truth (the data-generating parameters)."""

    respondent: str
    beta: np.ndarray
    part_worths: "OrderedDict[str, OrderedDict[str, float]]"
    must_have: dict[str, str] = field(default_factory=dict)
    unacceptable: dict[str, set[str]] = field(default_factory=dict)
    calibration_threshold: float = 0.0


# ---------------------------------------------------------------------------
# Default preference shapes + importance weights (overridable per attribute)
# ---------------------------------------------------------------------------
#: Attribute names whose levels are "lower is better" (cheaper preferred).
_DECREASING = {"price", "cost"}
#: Attribute names whose mid level is preferred (a peaked taste).
_PEAKED = {"display", "screen", "size"}
#: Attribute names treated as a mild ordered taste, favouring the first level.
_FIRST_FAVOURED = {"os", "operating_system", "brand"}

#: Planted importance weight per (known) attribute; price leads but never
#: dominates. Unknown attributes fall back to a gentle by-position schedule.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "price": 1.6,
    "processor": 1.3,
    "graphics": 1.2,
    "ram": 1.1,
    "storage": 1.0,
    "battery": 1.0,
    "display": 0.8,
    "os": 0.7,
    "touchscreen": 0.5,
}


def _default_shape(attribute: str, k: int) -> np.ndarray:
    """A length-``k`` preference shape over an attribute's levels (spec order)."""
    name = attribute.lower()
    if name in _DECREASING:
        return np.linspace(1.0, -1.0, k)
    if name in _PEAKED:
        return -np.abs(np.arange(k) - (k - 1) / 2.0)
    if name in _FIRST_FAVOURED:
        return np.linspace(0.5, -0.5, k)
    return np.linspace(-1.0, 1.0, k)  # default: more is better


def _default_weight(attribute: str, index: int, n_attributes: int) -> float:
    """Planted importance weight; known names win, else a gentle 1.2→0.8 ramp."""
    known = _DEFAULT_WEIGHTS.get(attribute.lower())
    if known is not None:
        return known
    if n_attributes <= 1:
        return 1.0
    return 1.2 - 0.4 * index / (n_attributes - 1)


# ---------------------------------------------------------------------------
# Population model
# ---------------------------------------------------------------------------
def population_from_spec(
    spec: QuestionnaireSpec,
    *,
    importance_weights: Mapping[str, float] | None = None,
    shapes: Mapping[str, Sequence[float]] | None = None,
    hetero_scale: float = 0.4,
) -> PopulationModel:
    """Build the planted :class:`PopulationModel` from a questionnaire spec.

    For each active attribute we lay a zero-centred, importance-weighted
    preference shape over its levels. The surviving-level values become the
    effects-coded ``mean_beta`` (so ``beta_to_level_utilities`` reproduces the
    full part-worths exactly), and heterogeneity SD is proportional to how much
    the attribute matters (``hetero_scale`` × planted range).
    """
    if hetero_scale < 0:
        raise ValueError(f"hetero_scale must be >= 0 (got {hetero_scale})")
    attribute_levels = attribute_levels_from_spec(spec)
    if not attribute_levels:
        raise ValueError("spec has no active attributes to simulate")
    n_attributes = len(attribute_levels)

    mean_part_worths: "OrderedDict[str, OrderedDict[str, float]]" = OrderedDict()
    part_worth_ranges: "OrderedDict[str, float]" = OrderedDict()
    column_names: list[str] = []
    mean_beta: list[float] = []
    hetero_sd: list[float] = []

    for index, (attribute, levels) in enumerate(attribute_levels.items()):
        k = len(levels)
        raw = (shapes or {}).get(attribute)
        shape = np.asarray(raw, dtype=float) if raw is not None else _default_shape(attribute, k)
        if shape.shape[0] != k:
            raise ValueError(f"shape for {attribute!r} must have {k} entries (got {shape.shape[0]})")
        weight = (importance_weights or {}).get(attribute)
        if weight is None:
            weight = _default_weight(attribute, index, n_attributes)
        centred = weight * (shape - shape.mean())  # sum-to-zero per attribute

        mean_part_worths[attribute] = OrderedDict(
            (level, float(centred[j])) for j, level in enumerate(levels)
        )
        attr_range = float(centred.max() - centred.min())
        part_worth_ranges[attribute] = attr_range
        for j, level in enumerate(levels[:-1]):  # drop last → effects-coded survivors
            column_names.append(f"{attribute}__{level}")
            mean_beta.append(float(centred[j]))
            hetero_sd.append(hetero_scale * attr_range)

    return PopulationModel(
        attribute_levels=attribute_levels,
        column_names=tuple(column_names),
        mean_beta=np.asarray(mean_beta, dtype=float),
        hetero_sd=np.asarray(hetero_sd, dtype=float),
        part_worth_ranges=part_worth_ranges,
        mean_part_worths=mean_part_worths,
    )


def draw_respondent_truth(
    pop: PopulationModel,
    respondent: str,
    rng: np.random.Generator,
    *,
    p_must_have: float = 0.35,
    p_unacceptable: float = 0.35,
) -> RespondentTruth:
    """Draw one respondent's true β + (occasional) B2 constraints.

    ``β_i = μ + σ ⊙ N(0, 1)`` (diagonal heterogeneity). A must-have is placed on
    the respondent's *most-valued* attribute's best level; an unacceptable on a
    different attribute's worst level. Probabilities are kept ≤ 0.4 so the
    constrained attribute still varies across the rest of the sample.
    """
    beta = pop.mean_beta + pop.hetero_sd * rng.standard_normal(pop.mean_beta.shape[0])
    part_worths = beta_to_level_utilities(beta, pop.column_names, pop.attribute_levels)

    ranges = {
        attribute: max(levels.values()) - min(levels.values())
        for attribute, levels in part_worths.items()
    }
    must_have: dict[str, str] = {}
    unacceptable: dict[str, set[str]] = {}

    if ranges and rng.random() < p_must_have:
        top = max(ranges, key=ranges.get)
        must_have[top] = max(part_worths[top], key=part_worths[top].get)

    if rng.random() < p_unacceptable:
        candidates = [a for a in pop.attribute_levels if a not in must_have]
        if candidates:
            attribute = candidates[int(rng.integers(0, len(candidates)))]
            if len(pop.attribute_levels[attribute]) > 1:
                worst = min(part_worths[attribute], key=part_worths[attribute].get)
                unacceptable[attribute] = {worst}

    return RespondentTruth(
        respondent=respondent,
        beta=beta,
        part_worths=part_worths,
        must_have=must_have,
        unacceptable=unacceptable,
        calibration_threshold=float(rng.normal(0.0, 0.5)),
    )


# ---------------------------------------------------------------------------
# Per-respondent stage builders
# ---------------------------------------------------------------------------
def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def _profile_utility(
    profile: Profile, part_worths: Mapping[str, Mapping[str, float]]
) -> float:
    """Sum of a profile's level part-worths under one respondent's utilities."""
    return float(
        sum(part_worths.get(attr, {}).get(code, 0.0) for attr, code in profile.levels)
    )


def _calibration_concepts(
    spec: QuestionnaireSpec,
    anchor: Profile,
    *,
    must_have: Mapping[str, str] | None,
    unacceptable: Mapping[str, set[str]] | None,
    n_concepts: int,
    seed: int,
) -> tuple[Profile, ...]:
    """Anchor + up to ``n_concepts-1`` distinct constraint-valid near-anchor variants.

    A Streamlit-free re-creation of ``survey_views.b5_calibration.calibration_concepts``
    (that module imports ``streamlit`` at import time).
    """
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
    for profile in filter_by_constraints(pool, must_have=must_have, unacceptable=unacceptable):
        if profile.levels in seen:
            continue
        seen.add(profile.levels)
        concepts.append(profile)
        if len(concepts) >= n_concepts:
            break
    return tuple(concepts)


def _background_records(
    questions: Sequence[BackgroundQuestion], respondent: str, rng: np.random.Generator
) -> list[R.BackgroundResponse]:
    """Sample a Part A answer per question (multi → 1..3 distinct, ``; ``-joined)."""
    records: list[R.BackgroundResponse] = []
    for index, question in enumerate(questions):
        options = list(question.options)
        if not options:
            continue
        if getattr(question, "multi", False):
            high = min(3, len(options))
            k = int(rng.integers(1, high + 1))
            picks = rng.choice(len(options), size=k, replace=False)
            answer = "; ".join(str(options[i]) for i in picks)
        else:
            answer = str(options[int(rng.integers(0, len(options)))])
        if answer:
            records.append(R.BackgroundResponse(respondent, index + 1, question.identifier, answer))
    return records


def _constraint_records(
    must_have: Mapping[str, str],
    unacceptable: Mapping[str, set[str]],
    respondent: str,
) -> list[R.ConstraintResponse]:
    """B2 must-have / unacceptable verdicts, one per flagged (attribute, level)."""
    records: list[R.ConstraintResponse] = []
    task_id = 0
    for attribute, level in must_have.items():
        task_id += 1
        records.append(R.ConstraintResponse(respondent, task_id, attribute, level, "must_have"))
    for attribute, levels in unacceptable.items():
        for level in levels:
            task_id += 1
            records.append(
                R.ConstraintResponse(respondent, task_id, attribute, level, "unacceptable")
            )
    return records


def _constraint_valid_pool(
    spec: QuestionnaireSpec,
    anchor: Profile,
    must_have: Mapping[str, str],
    unacceptable: Mapping[str, set[str]],
    *,
    pool_size: int,
    alts_per_task: int,
    rng: np.random.Generator,
) -> list[Profile]:
    """Anchor + distinct constraint-valid profiles, padded so a task can form."""
    candidates = generate_profiles(spec, n_profiles=pool_size, seed=int(rng.integers(0, 2**31 - 1)))
    pool: list[Profile] = [anchor]
    seen = {anchor.levels}
    for profile in filter_by_constraints(candidates, must_have=must_have, unacceptable=unacceptable):
        if profile.levels in seen:
            continue
        seen.add(profile.levels)
        pool.append(profile)
        if len(pool) >= 16:
            break
    if len(pool) < alts_per_task:  # contradictory constraints emptied the pool
        for profile in candidates:
            if profile.levels not in seen:
                seen.add(profile.levels)
                pool.append(profile)
            if len(pool) >= alts_per_task:
                break
    return pool


def _tournament_records(
    tasks: Sequence[Task],
    truth: RespondentTruth,
    pop: PopulationModel,
    rng: np.random.Generator,
    *,
    logit_alpha: float,
) -> list[R.TournamentResponse]:
    """Utility-driven choices: Gumbel-argmax over each task's systematic utilities."""
    records: list[R.TournamentResponse] = []
    for task in tasks:
        design = effects_code(task.alternatives, pop.attribute_levels)[0]
        utilities = logit_alpha * (design @ truth.beta)
        chosen = int(np.argmax(utilities + rng.gumbel(size=utilities.shape[0])))
        records.append(R.TournamentResponse(truth.respondent, task, chosen))
    return records


def _calibration_records(
    spec: QuestionnaireSpec,
    anchor: Profile,
    truth: RespondentTruth,
    *,
    n_concepts: int,
    cal_alpha: float,
    rng: np.random.Generator,
) -> list[R.CalibrationResponse]:
    """B5: 0..5 purchase probability rising with each concept's utility."""
    concepts = _calibration_concepts(
        spec,
        anchor,
        must_have=truth.must_have,
        unacceptable=truth.unacceptable,
        n_concepts=n_concepts,
        seed=int(rng.integers(0, 2**31 - 1)),
    )
    anchor_utility = _profile_utility(anchor, truth.part_worths)
    records: list[R.CalibrationResponse] = []
    for index, profile in enumerate(concepts):
        delta = _profile_utility(profile, truth.part_worths) - anchor_utility
        p = _sigmoid(cal_alpha * delta + truth.calibration_threshold)
        probability = int(rng.binomial(5, min(max(p, 0.0), 1.0)))
        records.append(R.CalibrationResponse(truth.respondent, index + 1, profile, probability))
    return records


def _wtp_records(
    wtp_features: Sequence[WtpFeature],
    amount_bands: Sequence[tuple[str, str]],
    wtp_feature_attribute: Mapping[str, str] | None,
    pop: PopulationModel,
    truth: RespondentTruth,
    rng: np.random.Generator,
) -> list[R.WtpResponse]:
    """Part C: pick a band per feature, higher when the respondent values it more.

    A feature that maps (via ``wtp_feature_attribute``) to a modelled attribute
    correlates with how far above the population that respondent values it;
    unmapped features fall back to a neutral draw (never raises).
    """
    bands = list(amount_bands)
    n_bands = len(bands)
    feature_attribute = dict(wtp_feature_attribute or {})
    records: list[R.WtpResponse] = []
    for index, feature in enumerate(wtp_features):
        attribute = feature_attribute.get(feature.identifier, feature.identifier)
        reference = pop.part_worth_ranges.get(attribute, 0.0)
        if attribute in truth.part_worths and reference > 0:
            per_level = truth.part_worths[attribute]
            personal = max(per_level.values()) - min(per_level.values())
            z = (personal - reference) / reference
            center = (n_bands - 1) / 2.0 + 1.5 * z
        else:
            center = rng.uniform(0.0, n_bands - 1)
        band_index = int(np.clip(round(center + rng.normal(0.0, 0.6)), 0, n_bands - 1))
        records.append(R.WtpResponse(truth.respondent, index + 1, feature.identifier, bands[band_index][0]))
    return records


# ---------------------------------------------------------------------------
# One respondent + the N-respondent orchestrator
# ---------------------------------------------------------------------------
def simulate_respondent(
    truth: RespondentTruth,
    spec: QuestionnaireSpec,
    pop: PopulationModel,
    rng: np.random.Generator,
    *,
    questions: Sequence[BackgroundQuestion],
    wtp_features: Sequence[WtpFeature],
    amount_bands: Sequence[tuple[str, str]],
    wtp_feature_attribute: Mapping[str, str] | None = None,
    n_tasks: int = 8,
    alts_per_task: int = 2,
    pool_size: int = 80,
    n_calibration: int = 3,
    logit_alpha: float = 1.0,
    cal_alpha: float = 1.2,
) -> pd.DataFrame:
    """Walk ONE respondent through all five stages → a long-format response frame."""
    attribute_levels = pop.attribute_levels
    anchor = anchor_from_ratings(
        {}, spec, must_have=truth.must_have, unacceptable=truth.unacceptable
    )
    pool = _constraint_valid_pool(
        spec, anchor, truth.must_have, truth.unacceptable,
        pool_size=pool_size, alts_per_task=alts_per_task, rng=rng,
    )
    tasks = build_tasks(
        tuple(pool), n_tasks=n_tasks, alts_per_task=alts_per_task,
        seed=int(rng.integers(0, 2**31 - 1)),
    )

    frames = [
        R.assemble_background_responses(
            _background_records(questions, truth.respondent, rng), attribute_levels
        ),
        R.assemble_musthave_responses(
            _constraint_records(truth.must_have, truth.unacceptable, truth.respondent),
            attribute_levels,
        ),
        R.assemble_tournament_responses(
            _tournament_records(tasks, truth, pop, rng, logit_alpha=logit_alpha),
            attribute_levels,
        ),
        R.assemble_calibration_responses(
            _calibration_records(
                spec, anchor, truth, n_concepts=n_calibration, cal_alpha=cal_alpha, rng=rng
            ),
            attribute_levels,
        ),
        R.assemble_wtp_responses(
            _wtp_records(
                wtp_features, amount_bands, wtp_feature_attribute, pop, truth, rng
            ),
            attribute_levels,
        ),
    ]
    return R.concat_responses(*frames)


def generate_synthetic_responses(
    spec: QuestionnaireSpec,
    *,
    questions: Sequence[BackgroundQuestion],
    wtp_features: Sequence[WtpFeature],
    amount_bands: Sequence[tuple[str, str]],
    wtp_feature_attribute: Mapping[str, str] | None = None,
    n_respondents: int = 200,
    seed: int = 2026,
    n_tasks: int = 8,
    alts_per_task: int = 2,
    pool_size: int = 80,
    n_calibration: int = 3,
    respondent_prefix: str = "r",
    logit_alpha: float = 1.0,
    cal_alpha: float = 1.2,
    hetero_scale: float = 0.4,
    importance_weights: Mapping[str, float] | None = None,
    shapes: Mapping[str, Sequence[float]] | None = None,
) -> tuple[pd.DataFrame, PopulationModel, list[RespondentTruth]]:
    """Simulate ``n_respondents`` and stack them into one long-format frame.

    Deterministic in ``seed``: each respondent draws from an independent child
    of a :class:`numpy.random.SeedSequence`, so adding respondents leaves the
    earlier ones byte-for-byte unchanged. Returns ``(frame, population, truths)``
    — the planted ground truth is handed back for tests and walkthroughs.
    """
    if n_respondents <= 0:
        raise ValueError(f"n_respondents must be positive (got {n_respondents})")

    pop = population_from_spec(
        spec, importance_weights=importance_weights, shapes=shapes, hetero_scale=hetero_scale
    )
    children = np.random.SeedSequence(seed).spawn(n_respondents)
    width = max(3, len(str(n_respondents)))

    frames: list[pd.DataFrame] = []
    truths: list[RespondentTruth] = []
    for index, child in enumerate(children):
        rng = np.random.default_rng(child)
        respondent = f"{respondent_prefix}{index + 1:0{width}d}"
        truth = draw_respondent_truth(pop, respondent, rng)
        frames.append(
            simulate_respondent(
                truth, spec, pop, rng,
                questions=questions, wtp_features=wtp_features, amount_bands=amount_bands,
                wtp_feature_attribute=wtp_feature_attribute,
                n_tasks=n_tasks, alts_per_task=alts_per_task, pool_size=pool_size,
                n_calibration=n_calibration, logit_alpha=logit_alpha, cal_alpha=cal_alpha,
            )
        )
        truths.append(truth)

    return R.concat_responses(*frames), pop, truths
