"""Tests for Module 4 weighted distance (``compute_distance_matrix``).

The convention under test (algorithm_spec.md §6): each z-scored value in a
column ``j`` belonging to attribute ``a`` is multiplied by ``√(RI_a / m_a)``,
so the squared per-column contribution to the Euclidean distance is
``(RI_a / m_a) · Δ_j²``. We model that as a per-column weight vector
``w_j = RI_a / m_a`` consumed by ``weighted_distance_matrix`` which computes
``√( Σ_j w_j · Δ_j² )``.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import compute_distance_matrix as cdm
from conjoint import io


# ---------------------------------------------------------------------------
# weighted_distance_matrix — hand-computed small case
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_weighted_distance_matrix_hand_computed() -> None:
    """2 products x 2 feature columns, known weights, by-hand check.

    d_w(A, B) = sqrt( w0 * (a0 - b0)^2 + w1 * (a1 - b1)^2 )
    """
    X = np.array([[0.0, 0.0], [3.0, 4.0]], dtype="float64")
    weights = np.array([1.0, 0.25], dtype="float64")

    D = cdm.weighted_distance_matrix(X, weights)

    # Δ = (3, 4); contribution = 1*9 + 0.25*16 = 9 + 4 = 13 -> sqrt(13).
    expected = math.sqrt(1.0 * 3.0**2 + 0.25 * 4.0**2)
    assert D.shape == (2, 2)
    assert D[0, 0] == 0.0
    assert D[1, 1] == 0.0
    assert D[0, 1] == pytest.approx(expected)
    assert D[1, 0] == pytest.approx(expected)
    # The √w_j multiplier interpretation must agree with the squared-weight form:
    # scaling each value by √w_j then taking plain Euclidean gives the same number.
    by_sqrt = math.sqrt((((X[0] - X[1]) * np.sqrt(weights)) ** 2).sum())
    assert D[0, 1] == pytest.approx(by_sqrt)


@pytest.mark.unit
def test_weighted_distance_zero_weight_drops_column() -> None:
    """A column with weight 0 contributes nothing to the distance."""
    X = np.array([[0.0, 100.0], [0.0, -100.0]], dtype="float64")
    weights = np.array([1.0, 0.0], dtype="float64")
    D = cdm.weighted_distance_matrix(X, weights)
    # Only the (identical) first column counts -> distance is 0.
    assert D[0, 1] == pytest.approx(0.0)


@pytest.mark.unit
def test_weighted_distance_matrix_rejects_bad_shapes() -> None:
    X = np.zeros((3, 2), dtype="float64")
    with pytest.raises(ValueError):
        cdm.weighted_distance_matrix(X, np.array([1.0]))  # wrong length
    with pytest.raises(ValueError):
        cdm.weighted_distance_matrix(X, np.array([1.0, -1.0]))  # negative weight


# ---------------------------------------------------------------------------
# weighted_distance_matrix — equivalence to the spec multiply-then-Euclidean
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_weighted_distance_equals_multiply_then_plain_euclidean() -> None:
    """Distance on √w_j-scaled columns equals weighted_distance_matrix."""
    rng = np.random.default_rng(7)
    X = rng.normal(size=(5, 4))
    weights = np.array([0.4, 0.1, 0.25, 0.25], dtype="float64")

    expected = cdm.compute_euclidean_distance_matrix(X * np.sqrt(weights))
    got = cdm.weighted_distance_matrix(X, weights)
    np.testing.assert_allclose(got, expected, atol=1e-12)


# ---------------------------------------------------------------------------
# build_weight_vector
# ---------------------------------------------------------------------------
def _importance_frame(ri_by_attr: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            io.ATTRIBUTE_COL: list(ri_by_attr),
            io.ABSOLUTE_IMPORTANCE_COL: [v * 100 for v in ri_by_attr.values()],
            io.RELATIVE_IMPORTANCE_COL: list(ri_by_attr.values()),
        }
    )


@pytest.mark.unit
def test_build_weight_vector_maps_columns_to_attribute_weights() -> None:
    columns = ["eng__a", "eng__b", "trans__x", "trans__y", "trans__z"]
    importance = _importance_frame({"eng": 0.4, "trans": 0.6})
    attribute_map = {
        "eng": {"columns": ["eng__a", "eng__b"], "m_a": 2},
        "trans": {"columns": ["trans__x", "trans__y", "trans__z"], "m_a": 3},
    }

    weights = cdm.build_weight_vector(columns, importance, attribute_map)

    # w_j = RI_a / m_a, shared across an attribute's columns.
    expected = np.array([0.4 / 2, 0.4 / 2, 0.6 / 3, 0.6 / 3, 0.6 / 3])
    np.testing.assert_allclose(weights, expected)


@pytest.mark.unit
def test_build_weight_vector_applies_fallback_to_unmapped_columns() -> None:
    columns = ["eng__a", "eng__b", "price", "weight"]
    importance = _importance_frame({"eng": 1.0})
    attribute_map = {"eng": {"columns": ["eng__a", "eng__b"], "m_a": 2}}

    # Default fallback (0.0): unmapped columns drop out.
    weights_default = cdm.build_weight_vector(columns, importance, attribute_map)
    np.testing.assert_allclose(weights_default, [0.5, 0.5, 0.0, 0.0])

    # Custom fallback is honoured for unmapped columns only.
    weights_custom = cdm.build_weight_vector(
        columns, importance, attribute_map, default_weight=0.123
    )
    np.testing.assert_allclose(weights_custom, [0.5, 0.5, 0.123, 0.123])


@pytest.mark.unit
def test_build_weight_vector_preserves_column_order() -> None:
    # Map declares columns in a different order than the matrix.
    columns = ["trans__z", "eng__a", "trans__x", "eng__b", "trans__y"]
    importance = _importance_frame({"eng": 0.5, "trans": 0.5})
    attribute_map = {
        "eng": {"columns": ["eng__a", "eng__b"], "m_a": 2},
        "trans": {"columns": ["trans__x", "trans__y", "trans__z"], "m_a": 3},
    }
    weights = cdm.build_weight_vector(columns, importance, attribute_map)
    np.testing.assert_allclose(
        weights, [0.5 / 3, 0.5 / 2, 0.5 / 3, 0.5 / 2, 0.5 / 3]
    )


@pytest.mark.unit
def test_build_weight_vector_raises_on_missing_importance() -> None:
    columns = ["eng__a"]
    importance = _importance_frame({"trans": 1.0})  # 'eng' absent
    attribute_map = {"eng": {"columns": ["eng__a"], "m_a": 1}}
    with pytest.raises(ValueError, match="missing from"):
        cdm.build_weight_vector(columns, importance, attribute_map)


@pytest.mark.unit
def test_build_weight_vector_raises_on_inconsistent_m_a() -> None:
    columns = ["eng__a", "eng__b"]
    importance = _importance_frame({"eng": 1.0})
    attribute_map = {"eng": {"columns": ["eng__a", "eng__b"], "m_a": 3}}
    with pytest.raises(ValueError, match="disagrees"):
        cdm.build_weight_vector(columns, importance, attribute_map)


@pytest.mark.unit
def test_build_weight_vector_rejects_negative_default() -> None:
    with pytest.raises(ValueError):
        cdm.build_weight_vector(["x"], _importance_frame({"a": 1.0}), {}, default_weight=-1.0)


# ---------------------------------------------------------------------------
# Uniform-weight equivalence (proportionality, NOT raw equality)
# ---------------------------------------------------------------------------
def _synthetic_uniform_setup(
    n_products: int = 8, k_attributes: int = 4, levels: int = 3, seed: int = 11
) -> tuple[np.ndarray, list[str], pd.DataFrame, dict]:
    """Synthetic data where every attribute has equal m_a and uniform RI.

    Each attribute expands into ``levels`` one-hot columns (equal m_a), and the
    relative importance is split evenly across the ``k_attributes`` (uniform RI).
    Under these conditions every per-column weight equals the same constant
    ``c = (1/K) / m``, so the weighted matrix is ``sqrt(c)`` times the technical
    matrix (a positive scalar multiple) and the neighbour rankings are identical.
    """
    rng = np.random.default_rng(seed)
    columns: list[str] = []
    attribute_map: dict[str, dict[str, object]] = {}
    for a in range(k_attributes):
        attr = f"attr{a}"
        cols = [f"{attr}__l{l}" for l in range(levels)]
        columns.extend(cols)
        attribute_map[attr] = {"columns": cols, "m_a": levels}

    X = rng.normal(size=(n_products, len(columns)))
    ri = 1.0 / k_attributes
    importance = pd.DataFrame(
        {
            io.ATTRIBUTE_COL: [f"attr{a}" for a in range(k_attributes)],
            io.ABSOLUTE_IMPORTANCE_COL: [ri * 100] * k_attributes,
            io.RELATIVE_IMPORTANCE_COL: [ri] * k_attributes,
        }
    )
    return X, columns, importance, attribute_map


@pytest.mark.unit
def test_uniform_weights_yield_proportional_matrix_and_same_rankings() -> None:
    X, columns, importance, attribute_map = _synthetic_uniform_setup()
    X_scaled = cdm.scale_matrix(X)

    technical = cdm.compute_euclidean_distance_matrix(X_scaled)
    weights = cdm.build_weight_vector(columns, importance, attribute_map)
    weighted = cdm.weighted_distance_matrix(X_scaled, weights)

    # Every weight is the same constant c = (1/K)/m -> sqrt(c) scaling.
    assert np.allclose(weights, weights[0])
    expected_scale = math.sqrt(float(weights[0]))

    # Proportionality: constant ratio on every off-diagonal entry.
    iu = np.triu_indices_from(technical, k=1)
    ratios = weighted[iu] / technical[iu]
    np.testing.assert_allclose(ratios, expected_scale, rtol=1e-9, atol=1e-12)
    # And the ratio is genuinely constant (one unique value up to fp noise).
    assert np.ptp(ratios) < 1e-9

    # NOT raw equality (it only holds up to scale) — confirm they differ.
    assert not np.allclose(weighted, technical)

    # Identical nearest-neighbour rankings (scaling preserves argsort order).
    for i in range(technical.shape[0]):
        tech_order = np.argsort(technical[i], kind="stable")
        wt_order = np.argsort(weighted[i], kind="stable")
        np.testing.assert_array_equal(tech_order, wt_order)


@pytest.mark.unit
def test_nonuniform_weights_can_change_rankings() -> None:
    """Sanity guard: with skewed weights the rankings need NOT match.

    Distinguishes the uniform-weight equivalence from a vacuous always-true
    assertion. We construct a case where one attribute dominates so a different
    neighbour wins.
    """
    # Product 0 differs from P1 only on attr A, from P2 only on attr B.
    X_scaled = np.array(
        [
            [0.0, 0.0],  # P0
            [1.0, 0.0],  # P1: differs on col 0 (attr A) by 1
            [0.0, 1.0],  # P2: differs on col 1 (attr B) by 1
        ],
        dtype="float64",
    )
    # Technical: P1 and P2 are equidistant from P0 (both differ by 1 on one col).
    technical = cdm.compute_euclidean_distance_matrix(X_scaled)
    assert technical[0, 1] == pytest.approx(technical[0, 2])
    # Tie at the technical level -> stable argsort would rank P1 before P2.

    # Down-weight attr A (col 0) and up-weight attr B (col 1): P1's only
    # difference is on the cheap column, so P1 becomes the nearer neighbour and
    # the technical tie is broken in its favour -> ranking differs from a
    # symmetric/uniform-weight world.
    weighted = cdm.weighted_distance_matrix(X_scaled, np.array([0.01, 1.0]))
    assert weighted[0, 1] < weighted[0, 2]


# ---------------------------------------------------------------------------
# Round-trip via conjoint.io.write_importance + build_weight_vector
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_round_trip_importance_csv_drives_weights(tmp_path: Path) -> None:
    columns = ["eng__a", "eng__b", "trans__x", "trans__y"]
    importance_df = pd.DataFrame(
        {
            io.ATTRIBUTE_COL: ["eng", "trans"],
            io.ABSOLUTE_IMPORTANCE_COL: [30.0, 70.0],
            io.RELATIVE_IMPORTANCE_COL: [0.3, 0.7],
        }
    )
    path = tmp_path / "importance.csv"
    io.write_importance(importance_df, path)

    loaded = io.read_importance(path)
    attribute_map = {
        "eng": {"columns": ["eng__a", "eng__b"], "m_a": 2},
        "trans": {"columns": ["trans__x", "trans__y"], "m_a": 2},
    }
    weights = cdm.build_weight_vector(columns, loaded, attribute_map)
    np.testing.assert_allclose(weights, [0.3 / 2, 0.3 / 2, 0.7 / 2, 0.7 / 2])


@pytest.mark.integration
def test_round_trip_attribute_map_json_drives_weights(tmp_path: Path) -> None:
    """End-to-end through both on-disk artifacts (importance.csv + map.json)."""
    columns = ["a__1", "a__2", "b__1", "price"]
    importance_df = pd.DataFrame(
        {
            io.ATTRIBUTE_COL: ["a", "b"],
            io.ABSOLUTE_IMPORTANCE_COL: [50.0, 50.0],
            io.RELATIVE_IMPORTANCE_COL: [0.5, 0.5],
        }
    )
    imp_path = tmp_path / "importance.csv"
    map_path = tmp_path / "attribute_column_map.json"
    io.write_importance(importance_df, imp_path)
    io.write_attribute_map(
        {
            "a": {"columns": ["a__1", "a__2"], "m_a": 2},
            "b": {"columns": ["b__1"], "m_a": 1},
        },
        map_path,
    )

    weights = cdm.build_weight_vector(
        columns,
        io.read_importance(imp_path),
        io.read_attribute_map(map_path),
        default_weight=0.0,
    )
    # a -> 0.5/2 each, b -> 0.5/1, price unmapped -> 0.0.
    np.testing.assert_allclose(weights, [0.25, 0.25, 0.5, 0.0])


# ---------------------------------------------------------------------------
# CLI / module hygiene
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_parse_args_defaults_to_technical() -> None:
    args = cdm.parse_args([])
    assert args.mode == "technical"
    assert args.importance is None
    assert args.attribute_map is None
    assert args.unmapped_weight == cdm.DEFAULT_UNMAPPED_WEIGHT


@pytest.mark.unit
def test_parse_args_weighted_flags() -> None:
    args = cdm.parse_args(
        [
            "--mode",
            "weighted",
            "--importance",
            "imp.csv",
            "--attribute-map",
            "map.json",
            "--unmapped-weight",
            "0.05",
        ]
    )
    assert args.mode == "weighted"
    assert args.importance == "imp.csv"
    assert args.attribute_map == "map.json"
    assert args.unmapped_weight == pytest.approx(0.05)


@pytest.mark.unit
def test_scale_matrix_zero_mean_unit_variance() -> None:
    rng = np.random.default_rng(3)
    X = rng.normal(loc=5.0, scale=2.0, size=(20, 3))
    Z = cdm.scale_matrix(X)
    np.testing.assert_allclose(Z.mean(axis=0), 0.0, atol=1e-12)
    np.testing.assert_allclose(Z.std(axis=0), 1.0, atol=1e-12)
