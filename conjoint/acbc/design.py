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

import logging
import random
from collections import OrderedDict
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from conjoint.questionnaire import QuestionnaireSpec

logger = logging.getLogger(__name__)

#: Mapping ``{attribute: (level_code, ...)}``.
AttributeLevels = Mapping[str, Sequence[str]]

#: One prohibited pair: two ``(attribute, level_code)`` cells that must never
#: co-occur inside the same profile (Sawtooth "prohibited combinations", §9.1).
ProhibitedPair = tuple[tuple[str, str], tuple[str, str]]


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


def _normalise_prohibited(
    prohibited: Sequence[ProhibitedPair] | None,
    attribute_levels: "OrderedDict[str, tuple[str, ...]]",
) -> tuple[ProhibitedPair, ...]:
    """Validate prohibited pairs against the known attribute/level universe.

    Each pair is ``((attr_a, level_a), (attr_b, level_b))`` and must reference
    two *different* attributes whose levels exist in ``attribute_levels``;
    otherwise a :class:`ValueError` is raised (fail fast at the boundary).
    """
    if not prohibited:
        return ()
    normalised: list[ProhibitedPair] = []
    for pair in prohibited:
        if len(pair) != 2:
            raise ValueError(f"prohibited entry must be a 2-tuple of cells, got {pair!r}")
        (attr_a, level_a), (attr_b, level_b) = pair
        if attr_a == attr_b:
            raise ValueError(
                f"prohibited pair must span two different attributes (got {attr_a!r} twice)"
            )
        for attribute, level in ((attr_a, level_a), (attr_b, level_b)):
            if attribute not in attribute_levels:
                raise ValueError(f"prohibited pair references unknown attribute {attribute!r}")
            if level not in attribute_levels[attribute]:
                raise ValueError(
                    f"prohibited pair references unknown level {level!r} of {attribute!r}"
                )
        normalised.append(((attr_a, level_a), (attr_b, level_b)))
    return tuple(normalised)


def _profile_violates(
    row_levels: Mapping[str, str], prohibited: Sequence[ProhibitedPair]
) -> bool:
    """Return whether a single ``{attribute: level}`` row hits a prohibited pair."""
    for (attr_a, level_a), (attr_b, level_b) in prohibited:
        if row_levels.get(attr_a) == level_a and row_levels.get(attr_b) == level_b:
            return True
    return False


def _count_violations(
    columns: "OrderedDict[str, list[str]]", prohibited: Sequence[ProhibitedPair]
) -> int:
    """Count profiles (rows) that contain at least one prohibited pair."""
    if not prohibited:
        return 0
    keys = list(columns.keys())
    n_rows = len(next(iter(columns.values()))) if columns else 0
    total = 0
    for index in range(n_rows):
        row = {attribute: columns[attribute][index] for attribute in keys}
        if _profile_violates(row, prohibited):
            total += 1
    return total


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
    prohibited: Sequence[ProhibitedPair] | None = None,
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

    ``prohibited`` lists ``((attr_a, level_a), (attr_b, level_b))`` pairs
    that must never co-occur (Sawtooth "prohibited combinations", §9.1).
    The 2-opt minimises violations *before* overlap (lexicographic score),
    a deterministic repair pass clears any residue, and — as a final safety
    net — any profile that still violates a constraint is dropped (logged),
    so the returned pool can be shorter than ``n_profiles`` only when the
    constraints are jointly unsatisfiable for the requested balance.
    """
    if n_profiles <= 0:
        raise ValueError(f"n_profiles must be positive (got {n_profiles})")
    attribute_levels = _coerce_attribute_levels(source)
    prohibited_pairs = _normalise_prohibited(prohibited, attribute_levels)
    rng = random.Random(seed)

    columns: "OrderedDict[str, list[str]]" = OrderedDict()
    for attribute, levels in attribute_levels.items():
        columns[attribute] = _balanced_sequence(levels, n_profiles, rng)

    columns = _minimise_pairwise_overlap(columns, rng, swap_iterations, prohibited_pairs)
    if prohibited_pairs:
        columns = _repair_prohibited(columns, prohibited_pairs, rng)

    profiles: list[Profile] = []
    for index in range(n_profiles):
        levels = tuple((attribute, columns[attribute][index]) for attribute in columns)
        profile = Profile(levels=levels)
        if prohibited_pairs and _profile_violates(profile.as_dict, prohibited_pairs):
            logger.warning(
                "Dropping profile %d — could not satisfy prohibited combinations: %s",
                index, profile.levels,
            )
            continue
        profiles.append(profile)
    return tuple(profiles)


def _pair_imbalance(left: Sequence[str], right: Sequence[str]) -> int:
    """Sum of squared deviations of every ``(left, right)`` level pair from uniform.

    The deviation is measured over the **full ``K_a × K_b`` grid** of level
    pairs — including pairs that never co-occur (count ``0``). The previous
    version divided by the number of *observed* pairs and so silently ignored
    zero-overlap combinations; a design where two levels never appear together
    would have looked perfectly balanced. Counting the empty cells makes the
    metric a faithful "minimal overlap" objective.
    """
    left_levels = sorted(set(left))
    right_levels = sorted(set(right))
    if not left_levels or not right_levels:
        return 0
    counts: dict[tuple[str, str], int] = {
        (a, b): 0 for a in left_levels for b in right_levels
    }
    for a, b in zip(left, right):
        counts[(a, b)] += 1
    n_cells = len(counts)  # K_a * K_b, including never-observed level pairs
    mean = sum(counts.values()) / n_cells
    return int(round(sum((c - mean) ** 2 for c in counts.values())))


def _total_pair_imbalance(columns: "OrderedDict[str, list[str]]") -> int:
    """Sum :func:`_pair_imbalance` across every unordered attribute pair."""
    keys = list(columns.keys())
    total = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            total += _pair_imbalance(columns[keys[i]], columns[keys[j]])
    return total


def _design_score(
    columns: "OrderedDict[str, list[str]]", prohibited: Sequence[ProhibitedPair]
) -> tuple[int, int]:
    """Lexicographic design score ``(prohibited_violations, overlap_imbalance)``.

    Comparing these tuples drives the 2-opt to eliminate prohibited
    combinations *first* and only then flatten overlap — no penalty weight to
    tune. With ``prohibited`` empty the first element is always ``0`` so the
    behaviour collapses to pure overlap minimisation.
    """
    return _count_violations(columns, prohibited), _total_pair_imbalance(columns)


def _minimise_pairwise_overlap(
    columns: "OrderedDict[str, list[str]]",
    rng: random.Random,
    iterations: int,
    prohibited: Sequence[ProhibitedPair] = (),
) -> "OrderedDict[str, list[str]]":
    """2-opt swap heuristic — swap one attribute's values across two rows.

    A swap preserves the per-attribute level balance (the swapped values
    are within the same column) while changing the joint distributions.
    We accept any swap that strictly reduces the lexicographic
    :func:`_design_score` (prohibited violations first, then overlap).
    """
    if len(columns) < 2 or iterations <= 0:
        return columns

    keys = list(columns.keys())
    n_rows = len(next(iter(columns.values())))
    if n_rows < 2:
        return columns

    best_score = _design_score(columns, prohibited)
    for _ in range(iterations):
        attribute = keys[rng.randrange(len(keys))]
        col = columns[attribute]
        i = rng.randrange(n_rows)
        j = rng.randrange(n_rows)
        if i == j or col[i] == col[j]:
            continue
        col[i], col[j] = col[j], col[i]
        new_score = _design_score(columns, prohibited)
        if new_score < best_score:
            best_score = new_score
        else:
            col[i], col[j] = col[j], col[i]  # revert
    return columns


def _repair_prohibited(
    columns: "OrderedDict[str, list[str]]",
    prohibited: Sequence[ProhibitedPair],
    rng: random.Random,
) -> "OrderedDict[str, list[str]]":
    """Clear residual prohibited combinations via balance-preserving swaps.

    For each still-violating row we try swapping one of the offending
    attributes' value with another row so that *both* rows end up valid. Swaps
    stay within a single column, so per-attribute level balance is untouched.
    Rows that cannot be repaired are left for the caller to drop.
    """
    keys = list(columns.keys())
    n_rows = len(next(iter(columns.values()))) if columns else 0
    offending_attrs = sorted({attr for pair in prohibited for attr, _level in pair})

    for index in range(n_rows):
        row = {attribute: columns[attribute][index] for attribute in keys}
        if not _profile_violates(row, prohibited):
            continue
        repaired = False
        for attribute in offending_attrs:
            order = list(range(n_rows))
            rng.shuffle(order)
            col = columns[attribute]
            for other in order:
                if other == index or col[other] == col[index]:
                    continue
                col[index], col[other] = col[other], col[index]
                row_i = {a: columns[a][index] for a in keys}
                row_o = {a: columns[a][other] for a in keys}
                if not _profile_violates(row_i, prohibited) and not _profile_violates(
                    row_o, prohibited
                ):
                    repaired = True
                    break
                col[index], col[other] = col[other], col[index]  # revert
            if repaired:
                break
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
