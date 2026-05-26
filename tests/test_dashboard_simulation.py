"""Tests for the dashboard ``simulation`` helpers.

Covers both the legacy ``simulate_removal`` nearest-neighbour path
and the new ``distance_histogram_data`` / ``share_transfer_table``
helpers that feed the upgraded "Product Removal" panel in ``app.py``.
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pandas as pd
import pytest

from dashboard.simulation import (
    distance_histogram_data,
    share_transfer_table,
    simulate_removal,
)


@pytest.fixture
def square_distance_matrix() -> tuple[np.ndarray, list[str], pd.DataFrame]:
    """A 4-product symmetric distance matrix used by several tests."""
    products = ["A", "B", "C", "D"]
    matrix = np.array(
        [
            [0.0, 0.20, 0.50, 0.90],
            [0.20, 0.0, 0.30, 0.70],
            [0.50, 0.30, 0.0, 0.40],
            [0.90, 0.70, 0.40, 0.0],
        ]
    )
    df = pd.DataFrame(matrix, index=products, columns=products)
    return matrix, products, df


@pytest.mark.unit
def test_simulate_removal_picks_closest_survivor(square_distance_matrix) -> None:
    matrix, products, df = square_distance_matrix
    result = simulate_removal(df, matrix, products_to_remove=["B"])

    assert "error" not in result
    assert result["substitutes"]["B"]["substitute"] == "A"
    assert result["substitutes"]["B"]["distance"] == pytest.approx(0.20)


@pytest.mark.unit
def test_simulate_removal_handles_empty_input(square_distance_matrix) -> None:
    _, _, df = square_distance_matrix
    result = simulate_removal(df, df.values, products_to_remove=[])
    assert "error" in result


@pytest.mark.unit
def test_distance_histogram_data_drops_removed_rows(square_distance_matrix) -> None:
    matrix, products, _ = square_distance_matrix
    before, after = distance_histogram_data(matrix, products, removed=["A"])
    # before is the upper triangle of the full 4x4 → 6 entries.
    assert before.size == 6
    # after drops A's row/col → 3x3 → 3 upper-triangle entries.
    assert after.size == 3


@pytest.mark.unit
def test_share_transfer_table_uses_acbc_simulation() -> None:
    # Two respondents with opposite preferences over a 2-attribute design.
    utilities_frame = pd.DataFrame(
        {
            "respondent": ["r1", "r2"],
            "engine__basic": [0.0, 0.5],
            "engine__premium": [0.5, 0.0],
            "cabin__open": [0.4, -0.1],
            "cabin__closed": [-0.4, 0.1],
        }
    )
    products = OrderedDict(
        A={"engine": "premium", "cabin": "closed"},
        B={"engine": "basic", "cabin": "open"},
    )
    level_map = OrderedDict(
        engine=["basic", "premium"],
        cabin=["open", "closed"],
    )
    transfer = share_transfer_table(
        utilities_frame, products, ["A"], level_map=level_map
    )
    assert set(transfer["product"]) == {"A", "B"}
    # A is removed → after_share == 0; B absorbs the entire share.
    after = transfer.set_index("product")["share_after"]
    assert after["A"] == pytest.approx(0.0)
    assert after["B"] == pytest.approx(1.0)
