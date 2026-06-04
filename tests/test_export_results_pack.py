"""Tests for ``scripts/export_results_pack.py`` (Exposé §3.3 results pack).

Covers the pure table/figure helpers and an end-to-end pack build into a temp
directory. The demo artifacts are rebuilt in ``tmp_path`` (mirroring
``test_validate_conjoint_build_report_round_trip``) so the test does not depend
on the gitignored ``outputs/`` tree and runs cleanly in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import compute_distance_matrix as cdm  # noqa: E402
import preprocessing as pp  # noqa: E402
from conjoint import io  # noqa: E402
from scripts import build_demo_importance as bdi  # noqa: E402
from scripts import build_demo_workbook as bdw  # noqa: E402
from scripts import export_results_pack as erp  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — a complete conjoint-demo dataset dir built in tmp_path
# ---------------------------------------------------------------------------
@pytest.fixture
def demo_dataset_dir(tmp_path: Path) -> Path:
    """Build importance + technical/weighted neighbours for the demo configs."""
    bdi.build(bdi.DEFAULT_REFERENCE, tmp_path / "importance.csv")
    workbook = tmp_path / "conjoint_demo.xlsx"
    bdw.build(bdw.DEFAULT_LEVELS, workbook)
    pre = tmp_path / "preprocessed_output.csv"
    amap = tmp_path / "attribute_column_map.json"
    pp.preprocess_workbook(workbook, pre, attribute_map=amap)

    X_scaled, columns, _ = cdm._prepare_scaled_matrix(str(pre))
    names = pd.read_excel(workbook, sheet_name="Edited")["product_id"].tolist()

    tech_dm = pd.DataFrame(
        cdm.compute_euclidean_distance_matrix(X_scaled), index=names, columns=names
    )
    cdm.build_neighbors_table(tech_dm, 5).to_csv(
        tmp_path / "nearest_neighbors.csv", index=False
    )

    importance = io.read_importance(tmp_path / "importance.csv")
    weights = cdm.build_weight_vector(columns, importance, io.read_attribute_map(amap))
    wt_dm = pd.DataFrame(
        cdm.weighted_distance_matrix(X_scaled, weights), index=names, columns=names
    )
    cdm.build_neighbors_table(wt_dm, 5).to_csv(
        tmp_path / "nearest_neighbors_weighted.csv", index=False
    )
    return tmp_path


# ---------------------------------------------------------------------------
# importance_pct_table
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_importance_pct_table_formats_percent_and_delta() -> None:
    importance = pd.DataFrame(
        {
            io.ATTRIBUTE_COL: ["engine", "tank"],
            io.ABSOLUTE_IMPORTANCE_COL: [1.0, 2.0],
            io.RELATIVE_IMPORTANCE_COL: [0.40, 0.60],
        }
    )
    lines = erp.importance_pct_table(importance, {"engine": 0.40, "tank": 0.55})
    body = "\n".join(lines)
    assert "| engine | 40.00% | 40.00% | +0.00 |" in body
    # 60% demo vs 55% reference -> +5.00 pp.
    assert "| tank | 60.00% | 55.00% | +5.00 |" in body


@pytest.mark.unit
def test_importance_pct_table_marks_absent_reference() -> None:
    importance = pd.DataFrame(
        {
            io.ATTRIBUTE_COL: ["mystery"],
            io.ABSOLUTE_IMPORTANCE_COL: [1.0],
            io.RELATIVE_IMPORTANCE_COL: [1.0],
        }
    )
    lines = erp.importance_pct_table(importance, {})
    assert "(absent)" in "\n".join(lines)


# ---------------------------------------------------------------------------
# nearest_distance_comparison
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_nearest_distance_comparison_normalises_by_view_mean() -> None:
    technical = pd.DataFrame(
        [("A", "B", 1.0), ("A", "C", 4.0), ("B", "A", 3.0), ("C", "A", 2.0)],
        columns=["product", "neighbor", "distance"],
    )
    weighted = pd.DataFrame(
        [("A", "C", 0.5), ("B", "A", 1.5), ("C", "A", 1.0)],
        columns=["product", "neighbor", "distance"],
    )
    comp = erp.nearest_distance_comparison(technical, weighted)
    assert list(comp.columns) == ["product", "technical", "customer_weighted"]
    # Each view is divided by its own mean nearest distance, so each normalised
    # column averages to 1.
    assert comp["technical"].mean() == pytest.approx(1.0)
    assert comp["customer_weighted"].mean() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# export_pack (end to end)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_export_pack_writes_all_expected_files(demo_dataset_dir: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "report_pack"
    erp.export_pack(
        demo_dataset_dir,
        bdi.DEFAULT_REFERENCE,
        demo_dataset_dir / "missing_report.md",  # absent: copy step is skipped
        out_dir,
    )

    for rel in (
        "README.md",
        "importance_n381.csv",
        "importance_n381.md",
        "neighbors_comparison.md",
        "figures/importance_pie.html",
        "figures/neighbor_shift_bar.html",
    ):
        assert (out_dir / rel).exists(), f"missing {rel}"

    # The validation report was absent, so it must NOT have been copied.
    assert not (out_dir / "validation_report_conjoint.md").exists()

    # importance.csv is copied verbatim.
    src = pd.read_csv(demo_dataset_dir / "importance.csv")
    copied = pd.read_csv(out_dir / "importance_n381.csv")
    pd.testing.assert_frame_equal(src, copied)

    # The neighbours comparison covers every configuration and states the count.
    nbr = (out_dir / "neighbors_comparison.md").read_text(encoding="utf-8")
    assert "configurations reorder their top-3" in nbr
    n_products = len(pd.read_csv(demo_dataset_dir / "nearest_neighbors.csv")["product"].unique())
    assert nbr.count("### `") == n_products

    # The figures are non-empty Plotly HTML.
    pie = (out_dir / "figures" / "importance_pie.html").read_text(encoding="utf-8")
    assert "plotly" in pie.lower() and len(pie) > 1000


@pytest.mark.integration
def test_export_pack_copies_validation_report_when_present(
    demo_dataset_dir: Path, tmp_path: Path
) -> None:
    report = demo_dataset_dir / "validation_report_conjoint.md"
    report.write_text("# stub report\n", encoding="utf-8")
    out_dir = tmp_path / "report_pack"
    erp.export_pack(demo_dataset_dir, bdi.DEFAULT_REFERENCE, report, out_dir)
    assert (out_dir / "validation_report_conjoint.md").read_text(
        encoding="utf-8"
    ) == "# stub report\n"
