"""Pure-function tests for the Module 5 comparative dashboard.

These tests never import or run Streamlit. They build synthetic CSV artifacts
in ``tmp_path`` (so they do not depend on the gitignored ``outputs/`` tree) and
exercise the pure helpers in ``dashboard.comparison`` plus the extended
``dataset_paths`` registry in ``dashboard.viz``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from dashboard import comparison, viz


# ---------------------------------------------------------------------------
# Synthetic-artifact builders
# ---------------------------------------------------------------------------
def _write_importance(path: Path) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "attribute": ["price", "battery", "camera"],
            "absolute_importance": [50.0, 30.0, 20.0],
            "relative_importance": [0.5, 0.3, 0.2],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def _write_neighbors(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a nearest_neighbors.csv in the Module 4 on-disk schema."""
    df = pd.DataFrame(rows, columns=["product", "neighbor_rank", "neighbor", "distance"])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _neighbors_table(tmp_path: Path, name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Round-trip a neighbours frame through CSV + ``load_neighbors_table``.

    Going through disk mirrors how ``app.py`` loads the artifacts and exercises
    the schema normalisation in ``viz.load_neighbors_table``.
    """
    path = tmp_path / name
    df.to_csv(path, index=False)
    return viz.load_neighbors_table(path)


# ---------------------------------------------------------------------------
# dataset_paths extension
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_dataset_paths_has_module5_keys(tmp_path: Path) -> None:
    paths = viz.dataset_paths(tmp_path, "smartphones")
    assert paths["dm_weighted"].name == "distance_matrix_weighted.csv"
    assert paths["nn_weighted"].name == "nearest_neighbors_weighted.csv"
    assert paths["importance"].name == "importance.csv"
    # All three live under the dataset folder.
    base = tmp_path / "smartphones"
    for key in ("dm_weighted", "nn_weighted", "importance"):
        assert paths[key].parent == base


# ---------------------------------------------------------------------------
# load_importance
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_load_importance_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "importance.csv"
    original = _write_importance(path)

    loaded = comparison.load_importance(path)

    assert list(loaded.columns) == [
        "attribute",
        "absolute_importance",
        "relative_importance",
    ]
    assert list(loaded["attribute"]) == ["price", "battery", "camera"]
    pd.testing.assert_series_equal(
        loaded["relative_importance"].reset_index(drop=True),
        original["relative_importance"].reset_index(drop=True),
    )
    # relative importances should still sum to 1.
    assert loaded["relative_importance"].sum() == pytest.approx(1.0)


@pytest.mark.unit
def test_load_importance_trims_attribute_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "importance.csv"
    pd.DataFrame(
        {
            "attribute": [" price ", "battery"],
            "absolute_importance": [60.0, 40.0],
            "relative_importance": [0.6, 0.4],
        }
    ).to_csv(path, index=False)

    loaded = comparison.load_importance(path)
    assert list(loaded["attribute"]) == ["price", "battery"]


# ---------------------------------------------------------------------------
# plot_importance_pie
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_plot_importance_pie_values_match_input(tmp_path: Path) -> None:
    path = tmp_path / "importance.csv"
    df = _write_importance(path)
    loaded = comparison.load_importance(path)

    fig = comparison.plot_importance_pie(loaded)

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "pie"
    assert list(trace.labels) == ["price", "battery", "camera"]
    assert list(trace.values) == pytest.approx(list(df["relative_importance"]))


@pytest.mark.unit
def test_plot_importance_pie_requires_columns() -> None:
    bad = pd.DataFrame({"attribute": ["a"], "something_else": [1.0]})
    with pytest.raises(ValueError):
        comparison.plot_importance_pie(bad)


# ---------------------------------------------------------------------------
# build_side_by_side_neighbors
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_build_side_by_side_aligns_same_order(tmp_path: Path) -> None:
    nn_tech = _neighbors_table(
        tmp_path,
        "nn_tech.csv",
        pd.DataFrame(
            {
                "product": ["A", "A", "B"],
                "neighbor_rank": [1, 2, 1],
                "neighbor": ["B", "C", "A"],
                "distance": [0.1, 0.4, 0.1],
            }
        ),
    )
    # Same neighbour order for A, different distances.
    nn_weighted = _neighbors_table(
        tmp_path,
        "nn_weighted.csv",
        pd.DataFrame(
            {
                "product": ["A", "A", "B"],
                "neighbor_rank": [1, 2, 1],
                "neighbor": ["B", "C", "A"],
                "distance": [0.2, 0.9, 0.2],
            }
        ),
    )

    table = comparison.build_side_by_side_neighbors(nn_tech, nn_weighted, "A", k=5)

    assert list(table["rank"]) == [1, 2]
    assert list(table["technical_neighbor"]) == ["B", "C"]
    assert list(table["weighted_neighbor"]) == ["B", "C"]
    assert list(table["technical_distance"]) == pytest.approx([0.1, 0.4])
    assert list(table["weighted_distance"]) == pytest.approx([0.2, 0.9])


@pytest.mark.unit
def test_build_side_by_side_aligns_different_orders(tmp_path: Path) -> None:
    """The two views rank different products at the same position."""
    nn_tech = _neighbors_table(
        tmp_path,
        "nn_tech.csv",
        pd.DataFrame(
            {
                "product": ["A", "A", "A"],
                "neighbor_rank": [1, 2, 3],
                "neighbor": ["B", "C", "D"],
                "distance": [0.1, 0.2, 0.3],
            }
        ),
    )
    # Weighted view re-orders: D is now the nearest, B drops to rank 3.
    nn_weighted = _neighbors_table(
        tmp_path,
        "nn_weighted.csv",
        pd.DataFrame(
            {
                "product": ["A", "A", "A"],
                "neighbor_rank": [1, 2, 3],
                "neighbor": ["D", "C", "B"],
                "distance": [0.05, 0.2, 0.6],
            }
        ),
    )

    table = comparison.build_side_by_side_neighbors(nn_tech, nn_weighted, "A", k=3)

    assert list(table["rank"]) == [1, 2, 3]
    # Technical column keeps technical order; weighted column keeps weighted order.
    assert list(table["technical_neighbor"]) == ["B", "C", "D"]
    assert list(table["weighted_neighbor"]) == ["D", "C", "B"]
    assert list(table["technical_distance"]) == pytest.approx([0.1, 0.2, 0.3])
    assert list(table["weighted_distance"]) == pytest.approx([0.05, 0.2, 0.6])


@pytest.mark.unit
def test_build_side_by_side_handles_unequal_neighbor_counts(tmp_path: Path) -> None:
    """When one view has fewer neighbours, extra ranks keep empty names."""
    nn_tech = _neighbors_table(
        tmp_path,
        "nn_tech.csv",
        pd.DataFrame(
            {
                "product": ["A", "A", "A"],
                "neighbor_rank": [1, 2, 3],
                "neighbor": ["B", "C", "D"],
                "distance": [0.1, 0.2, 0.3],
            }
        ),
    )
    nn_weighted = _neighbors_table(
        tmp_path,
        "nn_weighted.csv",
        pd.DataFrame(
            {
                "product": ["A"],
                "neighbor_rank": [1],
                "neighbor": ["C"],
                "distance": [0.15],
            }
        ),
    )

    table = comparison.build_side_by_side_neighbors(nn_tech, nn_weighted, "A", k=5)

    assert list(table["rank"]) == [1, 2, 3]
    assert list(table["technical_neighbor"]) == ["B", "C", "D"]
    assert list(table["weighted_neighbor"]) == ["C", "", ""]
    # Missing weighted distances are NaN beyond rank 1.
    assert table["weighted_distance"].iloc[0] == pytest.approx(0.15)
    assert pd.isna(table["weighted_distance"].iloc[1])
    assert pd.isna(table["weighted_distance"].iloc[2])


@pytest.mark.unit
def test_build_side_by_side_respects_k(tmp_path: Path) -> None:
    rows_tech = [
        {"product": "A", "neighbor_rank": r, "neighbor": n, "distance": float(r)}
        for r, n in enumerate(["B", "C", "D", "E"], start=1)
    ]
    nn = _neighbors_table(tmp_path, "nn.csv", pd.DataFrame(rows_tech))
    table = comparison.build_side_by_side_neighbors(nn, nn, "A", k=2)
    assert list(table["rank"]) == [1, 2]


# ---------------------------------------------------------------------------
# resolve_view
# ---------------------------------------------------------------------------
def _seed_technical(paths: dict[str, Path]) -> None:
    base = paths["base"]
    base.mkdir(parents=True, exist_ok=True)
    paths["dm"].write_text("x\n")
    paths["nn"].write_text("x\n")


@pytest.mark.unit
def test_resolve_view_technical_returns_technical_paths(tmp_path: Path) -> None:
    paths = viz.dataset_paths(tmp_path, "ds")
    _seed_technical(paths)

    resolved = comparison.resolve_view(paths, "technical")

    assert resolved["view"] == "technical"
    assert resolved["fell_back"] is False
    assert resolved["reason"] is None
    assert resolved["dm"] == paths["dm"]
    assert resolved["nn"] == paths["nn"]


@pytest.mark.unit
def test_resolve_view_weighted_when_present(tmp_path: Path) -> None:
    paths = viz.dataset_paths(tmp_path, "ds")
    _seed_technical(paths)
    paths["dm_weighted"].write_text("x\n")
    paths["nn_weighted"].write_text("x\n")
    _write_importance(paths["importance"])

    resolved = comparison.resolve_view(paths, "weighted")

    assert resolved["view"] == "weighted"
    assert resolved["fell_back"] is False
    assert resolved["reason"] is None
    assert resolved["dm"] == paths["dm_weighted"]
    assert resolved["nn"] == paths["nn_weighted"]
    assert resolved["importance"] == paths["importance"]


@pytest.mark.unit
def test_resolve_view_falls_back_when_weighted_missing(tmp_path: Path) -> None:
    paths = viz.dataset_paths(tmp_path, "ds")
    _seed_technical(paths)
    # importance present, but weighted distance/neighbour files are absent.
    _write_importance(paths["importance"])

    resolved = comparison.resolve_view(paths, "weighted")

    assert resolved["view"] == "technical"
    assert resolved["requested"] == "weighted"
    assert resolved["fell_back"] is True
    assert isinstance(resolved["reason"], str)
    assert "distance_matrix_weighted.csv" in resolved["reason"]
    assert resolved["dm"] == paths["dm"]
    assert resolved["nn"] == paths["nn"]


@pytest.mark.unit
def test_resolve_view_falls_back_when_importance_missing(tmp_path: Path) -> None:
    paths = viz.dataset_paths(tmp_path, "ds")
    _seed_technical(paths)
    paths["dm_weighted"].write_text("x\n")
    paths["nn_weighted"].write_text("x\n")
    # importance.csv intentionally absent.

    resolved = comparison.resolve_view(paths, "weighted")

    assert resolved["fell_back"] is True
    assert "importance.csv" in resolved["reason"]
    assert resolved["dm"] == paths["dm"]


@pytest.mark.unit
def test_resolve_view_rejects_bad_view(tmp_path: Path) -> None:
    paths = viz.dataset_paths(tmp_path, "ds")
    with pytest.raises(ValueError):
        comparison.resolve_view(paths, "nonsense")


# ---------------------------------------------------------------------------
# weight_importance_to_relative
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_weight_importance_to_relative_sums_to_one() -> None:
    weights = comparison.weight_importance_to_relative(
        {"price": "high", "battery": "medium", "camera": "low"}
    )
    assert sum(weights.values()) == pytest.approx(1.0)
    assert set(weights) == {"price", "battery", "camera"}


@pytest.mark.unit
def test_weight_importance_to_relative_is_monotonic() -> None:
    weights = comparison.weight_importance_to_relative(
        {
            "a": "high",
            "b": "medium-high",
            "c": "medium",
            "d": "low-medium",
            "e": "low",
        }
    )
    ordered = [weights["a"], weights["b"], weights["c"], weights["d"], weights["e"]]
    # Strictly decreasing high -> low.
    assert all(ordered[i] > ordered[i + 1] for i in range(len(ordered) - 1))


@pytest.mark.unit
def test_weight_importance_to_relative_drops_none() -> None:
    weights = comparison.weight_importance_to_relative(
        {"price": "high", "ignored": "none", "battery": "high"}
    )
    assert "ignored" not in weights
    assert weights["price"] == pytest.approx(0.5)
    assert weights["battery"] == pytest.approx(0.5)
    assert sum(weights.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_weight_importance_to_relative_all_none_is_empty() -> None:
    assert comparison.weight_importance_to_relative({"a": "none", "b": "none"}) == {}
    assert comparison.weight_importance_to_relative({}) == {}


@pytest.mark.unit
def test_weight_importance_to_relative_accepts_aliases() -> None:
    weights = comparison.weight_importance_to_relative(
        {"a": "Medium High", "b": "low_medium"}
    )
    # 'medium high' -> medium-high (score 4), 'low_medium' -> low-medium (score 2)
    assert weights["a"] == pytest.approx(4.0 / 6.0)
    assert weights["b"] == pytest.approx(2.0 / 6.0)


@pytest.mark.unit
def test_weight_importance_to_relative_rejects_unknown_label() -> None:
    with pytest.raises(ValueError):
        comparison.weight_importance_to_relative({"a": "super-high"})
