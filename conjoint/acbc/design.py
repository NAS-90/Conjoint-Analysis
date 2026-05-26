"""ACBC experimental design — profile pool + level balance + effects coding.

Implements the front half of the ACBC algorithm (Phase 2 §2):

* :func:`generate_profiles` — sample a balanced profile pool from the
  questionnaire spec. Each attribute's levels appear approximately
  uniformly often (``level balance``) and a 2-opt swap heuristic reduces
  pairwise level co-occurrence (``minimal overlap``).
* :func:`effects_code` — turn a profile pool into a numerical design
  matrix using **effects coding**: a ``K``-level attribute is encoded as
  ``K-1`` columns where level ``i`` (i < K-1) is ``+1`` in column ``i``
  and ``0`` elsewhere, and the *last* level is ``-1`` across every
  column. This is the standard ACBC parametrisation: the dropped level's
  utility is recovered as ``-Σ`` of the surviving levels' β.
* :func:`check_level_balance`, :func:`check_orthogonality` — design
  diagnostics consumed by tests and the validation report.

The module is dependency-light (numpy + the standard library). The
``QuestionnaireSpec`` lives in :mod:`conjoint.questionnaire`; we accept
either a spec or a plain ``{attribute: [level_code, ...]}`` mapping so the
design code can be exercised in tests without a workbook.
"""

from __future__ import annotations

import random
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from conjoint.questionnaire import QuestionnaireSpec

#: Mapping ``{attribute: (level_code, ...)}``.
AttributeLevels = Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class Profile:
    """One combination of attribute -> level, immutable."""

    levels: tuple[tuple[str, str], ...]  # ((attribute, level_code), ...)

    @property
    def as_dict(self) -> "OrderedDict[str, str]":
        """``OrderedDict({attribute: level_code, ...})`` preserving order."""
        return OrderedDict(self.levels)

    def level_for(self, attribute: str) -> str:
        """Return this profile's level for ``attribute``."""
        for attr, code in self.levels:
            if attr == attribute:
                return code
        raise KeyError(f"profile has no level for attribute {attribute!r}")


# ---------------------------------------------------------------------------
# Spec -> attribute_levels dict
# ---------------------------------------------------------------------------
def attribute_levels_from_spec(spec: QuestionnaireSpec) -> "OrderedDict[str, tuple[str, ...]]":
    """Extract ``{attribute: (level_code, ...)}`` from the **active** spec.

    Inactive attributes (e.g. B2 / B3 / C-WTP rows that the MVP doesn't
    model) are skipped so design generation only spans Part B-1.
    """
    result: "OrderedDict[str, tuple[str, ...]]" = OrderedDict()
    for attr in spec.active_attributes:
        result[attr.feature_name] = tuple(level.code for level in attr.levels)
    return result


def _coerce_attribute_levels(
    source: AttributeLevels | QuestionnaireSpec,
) -> "OrderedDict[str, tuple[str, ...]]":
    """Accept either a spec or a plain attribute->levels mapping."""
    if isinstance(source, QuestionnaireSpec):
        return attribute_levels_from_spec(source)
    result: "OrderedDict[str, tuple[str, ...]]" = OrderedDict()
    for attribute, levels in source.items():
        codes = tuple(str(code) for code in levels)
        if not codes:
            raise ValueError(f"attribute {attribute!r} has no levels")
        result[attribute] = codes
    if not result:
        raise ValueError("at least one attribute is required to generate profiles")
    return result


# ---------------------------------------------------------------------------
# Profile generation — balanced sampling
# ---------------------------------------------------------------------------
def _balanced_sequence(levels: Sequence[str], n: int, rng: random.Random) -> list[str]:
    """Return ``n`` levels with as-even-as-possible frequencies (shuffled).

    The base counts come from ``divmod(n, K)`` so every level appears at
    least ``n // K`` times; the remainder is sprinkled across the first
    ``n % K`` levels. The resulting list is shuffled to avoid positional
    bias.
    """
    k = len(levels)
    if k == 0:
        return []
    base, extra = divmod(n, k)
    counts = [base + (1 if i < extra else 0) for i in range(k)]
    bag: list[str] = []
    for code, count in zip(levels, counts):
        bag.extend([code] * count)
    rng.shuffle(bag)
    return bag


def generate_profiles(
    source: AttributeLevels | QuestionnaireSpec,
    n_profiles: int,
    *,
    seed: int | None = None,
    swap_iterations: int = 1_000,
) -> tuple[Profile, ...]:
    """Generate ``n_profiles`` near-balanced profiles.

    For each attribute we draw an independent balanced shuffle of its
    levels (``_balanced_sequence``) and combine them column-wise to form
    profiles. We then run ``swap_iterations`` of a 2-opt swap heuristic
    that reduces pairwise *level co-occurrence* — i.e. ``minimal
    overlap``: if levels ``(a₁, b₁)`` co-occur with high count and
    ``(a₂, b₁)`` with low count, swapping the ``b`` slot in two rows
    flattens the joint distribution while preserving each attribute's
    own level balance.
    """
    if n_profiles <= 0:
        raise ValueError(f"n_profiles must be positive (got {n_profiles})")
    attribute_levels = _coerce_attribute_levels(source)
    rng = random.Random(seed)

    columns: "OrderedDict[str, list[str]]" = OrderedDict()
    for attribute, levels in attribute_levels.items():
        columns[attribute] = _balanced_sequence(levels, n_profiles, rng)

    columns = _minimise_pairwise_overlap(columns, rng, swap_iterations)

    profiles: list[Profile] = []
    for index in range(n_profiles):
        levels = tuple((attribute, columns[attribute][index]) for attribute in columns)
        profiles.append(Profile(levels=levels))
    return tuple(profiles)


def _pair_imbalance(left: Sequence[str], right: Sequence[str]) -> int:
    """Sum of squared deviations of ``(left, right)`` pair counts from mean."""
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for a, b in zip(left, right):
        counts[(a, b)] += 1
    if not counts:
        return 0
    mean = sum(counts.values()) / len(counts)
    return int(round(sum((c - mean) ** 2 for c in counts.values())))


def _total_pair_imbalance(columns: "OrderedDict[str, list[str]]") -> int:
    """Sum :func:`_pair_imbalance` across every unordered attribute pair."""
    keys = list(columns.keys())
    total = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            total += _pair_imbalance(columns[keys[i]], columns[keys[j]])
    return total


def _minimise_pairwise_overlap(
    columns: "OrderedDict[str, list[str]]",
    rng: random.Random,
    iterations: int,
) -> "OrderedDict[str, list[str]]":
    """2-opt swap heuristic — swap one attribute's values across two rows.

    A swap preserves the per-attribute level balance (the swapped values
    are within the same column) while changing the joint distributions.
    We accept any swap that strictly reduces the global pair-imbalance.
    """
    if len(columns) < 2 or iterations <= 0:
        return columns

    keys = list(columns.keys())
    n_rows = len(next(iter(columns.values())))
    if n_rows < 2:
        return columns

    best_score = _total_pair_imbalance(columns)
    for _ in range(iterations):
        attribute = keys[rng.randrange(len(keys))]
        col = columns[attribute]
        i = rng.randrange(n_rows)
        j = rng.randrange(n_rows)
        if i == j or col[i] == col[j]:
            continue
        col[i], col[j] = col[j], col[i]
        new_score = _total_pair_imbalance(columns)
        if new_score < best_score:
            best_score = new_score
        else:
            col[i], col[j] = col[j], col[i]  # revert
    return columns


# ---------------------------------------------------------------------------
# Effects coding
# ---------------------------------------------------------------------------
def effects_code(
    profiles: Sequence[Profile],
    source: AttributeLevels | QuestionnaireSpec,
) -> tuple[np.ndarray, list[str], "OrderedDict[str, list[str]]"]:
    """Effects-code ``profiles`` against ``source``'s level definitions.

    Returns ``(X, column_names, level_map)`` where:

    * ``X`` has shape ``(n_profiles, Σ (K_a - 1))``; for attribute ``a``
      with levels ``[l_0, ..., l_{K-1}]`` we emit ``K-1`` columns; the
      ``i``-th column carries ``+1`` for level ``l_i`` (i < K-1), ``-1``
      for the dropped level ``l_{K-1}``, and ``0`` otherwise.
    * ``column_names`` are ``"{attribute}__{level_code}"`` strings, one
      per surviving level (the dropped level is excluded).
    * ``level_map`` is the attribute->ordered-levels mapping that was
      used for coding (the dropped level is *included* — utility for it
      is reconstructed as the negative sum of the surviving betas).
    """
    attribute_levels = _coerce_attribute_levels(source)
    level_map: "OrderedDict[str, list[str]]" = OrderedDict(
        (attribute, list(levels)) for attribute, levels in attribute_levels.items()
    )

    column_names: list[str] = []
    column_spec: list[tuple[str, str, str]] = []  # (attribute, surviving_level, dropped_level)
    for attribute, levels in attribute_levels.items():
        if len(levels) < 2:
            raise ValueError(
                f"attribute {attribute!r} needs at least 2 levels for effects coding"
            )
        dropped = levels[-1]
        for code in levels[:-1]:
            column_names.append(f"{attribute}__{code}")
            column_spec.append((attribute, code, dropped))

    matrix = np.zeros((len(profiles), len(column_names)), dtype=float)
    for row, profile in enumerate(profiles):
        chosen = profile.as_dict
        for col, (attribute, surviving, dropped) in enumerate(column_spec):
            level = chosen.get(attribute)
            if level == surviving:
                matrix[row, col] = 1.0
            elif level == dropped:
                matrix[row, col] = -1.0
            # else 0 — another surviving level handled by its own column
    return matrix, column_names, level_map


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------
def check_level_balance(
    profiles: Sequence[Profile],
    source: AttributeLevels | QuestionnaireSpec,
) -> "OrderedDict[str, OrderedDict[str, int]]":
    """Return ``{attribute: {level_code: count}}`` across ``profiles``."""
    attribute_levels = _coerce_attribute_levels(source)
    counts: "OrderedDict[str, OrderedDict[str, int]]" = OrderedDict()
    for attribute, levels in attribute_levels.items():
        counts[attribute] = OrderedDict((code, 0) for code in levels)
    for profile in profiles:
        for attribute, code in profile.levels:
            if attribute in counts and code in counts[attribute]:
                counts[attribute][code] += 1
    return counts


def level_balance_deviation(
    profiles: Sequence[Profile],
    source: AttributeLevels | QuestionnaireSpec,
) -> float:
    """Max absolute deviation between any level's count and the per-attribute mean.

    Returns ``0`` for a perfectly balanced design (every level appears
    ``n_profiles / K`` times). The metric is the worst per-attribute
    spread (``max_count - min_count``).
    """
    counts = check_level_balance(profiles, source)
    worst = 0
    for per_level in counts.values():
        values = list(per_level.values())
        if not values:
            continue
        worst = max(worst, max(values) - min(values))
    return float(worst)


def check_orthogonality(matrix: np.ndarray) -> float:
    """Largest absolute off-diagonal of ``XᵀX / n`` — 0 ⇒ fully orthogonal.

    For a balanced effects-coded design this number is small but rarely
    zero (effects coding is not fully orthogonal across attributes when
    level counts differ). The test suite only requires it to stay below
    a sensible bound; the validation report surfaces the actual value.
    """
    if matrix.size == 0:
        return 0.0
    gram = matrix.T @ matrix / matrix.shape[0]
    if gram.shape[0] <= 1:
        return 0.0
    mask = ~np.eye(gram.shape[0], dtype=bool)
    return float(np.max(np.abs(gram[mask])))
