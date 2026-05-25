"""Export a self-contained results pack for the report / slides (Exposé §3.3).

One command bundles the conjoint demo's headline results into
``outputs/report_pack/`` so they can be dropped straight into the 15–20 page
report and the slide deck, without re-running the dashboard::

    outputs/report_pack/
      README.md                       # how to reproduce this pack
      importance_n381.csv             # copy of the demo importance.csv
      importance_n381.md              # RI %% table, demo vs published N=381 study
      neighbors_comparison.md         # technical vs weighted top-k for ALL configs
      figures/
        importance_pie.html           # offline Plotly pie (relative importance)
        neighbor_shift_bar.html       # nearest-neighbour distance, tech vs weighted
      validation_report_conjoint.md   # copy of the latest validation report

The tables and figures re-use the report helpers in
``validation/validate_conjoint.py`` and the Plotly helpers in
``dashboard/comparison.py``, so there is a single source of truth.

Usage (from Distance-Analysis/, after ``./run.sh conjoint``)::

    python scripts/export_results_pack.py
    python scripts/export_results_pack.py \
        --dataset-dir outputs/conjoint_demo --out-dir outputs/report_pack
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow ``python scripts/export_results_pack.py``
    sys.path.insert(0, str(ROOT))

from conjoint.io import (  # noqa: E402  (import after sys.path bootstrap)
    ATTRIBUTE_COL,
    RELATIVE_IMPORTANCE_COL,
    read_importance,
)
from dashboard.comparison import load_importance, plot_importance_pie  # noqa: E402
from dashboard.viz import load_neighbors_table  # noqa: E402
from validation.validate_conjoint import _load_reference, neighbor_sections  # noqa: E402

DEFAULT_DATASET_DIR = ROOT / "outputs" / "conjoint_demo"
DEFAULT_REFERENCE = ROOT / "tests" / "fixtures" / "n381" / "importance_reference.json"
DEFAULT_VALIDATION_REPORT = ROOT / "validation" / "validation_report_conjoint.md"
DEFAULT_OUT_DIR = ROOT / "outputs" / "report_pack"

#: How many neighbours per configuration to show in the comparison table.
NEIGHBOR_K = 3


# ---------------------------------------------------------------------------
# Markdown — importance table (percentages)
# ---------------------------------------------------------------------------
def importance_pct_table(
    importance: pd.DataFrame, reference: dict[str, float]
) -> list[str]:
    """Markdown relative-importance table in percent, demo vs N=381 reference.

    The ``Δ (pp)`` column is in percentage points; it is ~0 because the demo
    re-uses the published study weights rather than fabricating them.
    """
    lines = [
        "| Attribute | Demo RI | Published N=381 RI | Δ (pp) |",
        "|---|---:|---:|---:|",
    ]
    for _, row in importance.iterrows():
        attr = str(row[ATTRIBUTE_COL])
        demo_pct = float(row[RELATIVE_IMPORTANCE_COL]) * 100.0
        ref = reference.get(attr)
        if ref is None:
            lines.append(f"| {attr} | {demo_pct:.2f}% | (absent) | — |")
        else:
            ref_pct = ref * 100.0
            lines.append(
                f"| {attr} | {demo_pct:.2f}% | {ref_pct:.2f}% "
                f"| {demo_pct - ref_pct:+.2f} |"
            )
    return lines


# ---------------------------------------------------------------------------
# Figure — nearest-neighbour distance, technical vs customer-weighted
# ---------------------------------------------------------------------------
def _nearest_distance(neighbors: pd.DataFrame) -> pd.Series:
    """Rank-1 (nearest) neighbour distance per product."""
    return neighbors.groupby("product")["distance"].min()


def nearest_distance_comparison(
    technical: pd.DataFrame, weighted: pd.DataFrame
) -> pd.DataFrame:
    """Per-product nearest-neighbour distance, normalised by each view's mean.

    Raw technical and customer-weighted distances live on different numeric
    scales, so comparing them directly is misleading. Each view is therefore
    divided by its own mean nearest-neighbour distance: a value above 1 means
    the product is *more isolated* than the typical configuration in that view.
    Putting the two normalised series side by side shows where re-weighting by
    customer importance changes how crowded a product's neighbourhood is.

    Output columns: ``product``, ``technical``, ``customer_weighted``.
    """
    tech = _nearest_distance(technical)
    wt = _nearest_distance(weighted)
    products = sorted(set(tech.index) & set(wt.index))

    tech_mean = float(tech.mean()) if len(tech) else 0.0
    wt_mean = float(wt.mean()) if len(wt) else 0.0

    rows = [
        {
            "product": product,
            "technical": tech[product] / tech_mean if tech_mean else 0.0,
            "customer_weighted": wt[product] / wt_mean if wt_mean else 0.0,
        }
        for product in products
    ]
    return pd.DataFrame(rows, columns=["product", "technical", "customer_weighted"])


def plot_nearest_distance_bar(comparison: pd.DataFrame) -> go.Figure:
    """Grouped bar of normalised nearest-neighbour distance per configuration."""
    long = comparison.melt(
        id_vars="product",
        value_vars=["technical", "customer_weighted"],
        var_name="view",
        value_name="relative_distance",
    )
    fig = px.bar(
        long,
        x="product",
        y="relative_distance",
        color="view",
        barmode="group",
        title="Nearest-neighbour distance relative to each view's mean",
    )
    fig.update_layout(
        xaxis_title="configuration",
        yaxis_title="nearest distance ÷ view mean",
        legend_title_text="view",
    )
    fig.add_hline(y=1.0, line_dash="dot", annotation_text="view mean")
    return fig


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------
def _readme(dataset_dir: Path, n_products: int, n_differing: int, k: int) -> str:
    """Render the pack's README explaining contents and how to reproduce it."""
    lines = [
        "# Conjoint results pack",
        "",
        "Headline outputs of the customer-weighted conjoint demo, bundled for the "
        "report and slides. Generated by `scripts/export_results_pack.py` from "
        f"`{dataset_dir}`.",
        "",
        "## Contents",
        "",
        "- `importance_n381.csv` — relative importance per attribute "
        "(the published N=381 tractor study weights).",
        "- `importance_n381.md` — the same table in percent, beside the published "
        "reference (Δ ≈ 0, i.e. authentic weights, not fabricated).",
        f"- `neighbors_comparison.md` — technical vs customer-weighted top-{k} "
        f"neighbours for all {n_products} configurations.",
        "- `figures/importance_pie.html` — relative-importance pie (offline Plotly).",
        "- `figures/neighbor_shift_bar.html` — nearest-neighbour distance per "
        "configuration, normalised within each view.",
        "- `validation_report_conjoint.md` — copy of the full validation report.",
        "",
        "## Headline finding",
        "",
        f"{n_differing} of {n_products} configurations reorder their top-{k} nearest "
        "neighbours once distance is weighted by what customers care about — the "
        "technical and customer-weighted views are not interchangeable.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "./run.sh conjoint                  # regenerate outputs/conjoint_demo/",
        "python scripts/export_results_pack.py",
        "```",
        "",
        "Open the `figures/*.html` files in a browser; print to PDF for the report "
        "appendix if needed.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def export_pack(
    dataset_dir: Path,
    reference_path: Path,
    validation_report: Path,
    out_dir: Path,
    *,
    k: int = NEIGHBOR_K,
) -> Path:
    """Build the full results pack under ``out_dir``; return ``out_dir``."""
    importance = read_importance(dataset_dir / "importance.csv")
    reference = _load_reference(reference_path)
    technical = load_neighbors_table(dataset_dir / "nearest_neighbors.csv")
    weighted = load_neighbors_table(dataset_dir / "nearest_neighbors_weighted.csv")
    products = sorted(technical["product"].unique())

    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. raw importance.csv (verbatim copy)
    shutil.copyfile(dataset_dir / "importance.csv", out_dir / "importance_n381.csv")

    # 2. importance markdown (percentages vs reference)
    imp_lines = [
        "# Customer importance — demo vs published N=381 study",
        "",
        "Relative importance per attribute. The demo re-uses the published study "
        "weights, so the Δ column is ~0 percentage points.",
        "",
        *importance_pct_table(importance, reference),
        "",
    ]
    (out_dir / "importance_n381.md").write_text(
        "\n".join(imp_lines) + "\n", encoding="utf-8"
    )

    # 3. full neighbour comparison (all configs) — reuse the validation helper
    section_lines, n_differing = neighbor_sections(technical, weighted, products, k=k)
    nbr_lines = [
        f"# Technical vs customer-weighted neighbours (top-{k}, all "
        f"{len(products)} configurations)",
        "",
        f"{n_differing} of {len(products)} configurations reorder their top-{k} "
        "nearest neighbours when distance is weighted by customer importance.",
        "",
        *section_lines,
    ]
    (out_dir / "neighbors_comparison.md").write_text(
        "\n".join(nbr_lines) + "\n", encoding="utf-8"
    )

    # 4. figures
    pie = plot_importance_pie(load_importance(dataset_dir / "importance.csv"))
    pie.write_html(figures_dir / "importance_pie.html", include_plotlyjs="cdn")
    bar = plot_nearest_distance_bar(nearest_distance_comparison(technical, weighted))
    bar.write_html(figures_dir / "neighbor_shift_bar.html", include_plotlyjs="cdn")

    # 5. validation report (copy if present)
    if Path(validation_report).exists():
        shutil.copyfile(validation_report, out_dir / "validation_report_conjoint.md")

    # 6. README
    (out_dir / "README.md").write_text(
        _readme(dataset_dir, len(products), n_differing, k), encoding="utf-8"
    )

    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument(
        "--validation-report", type=Path, default=DEFAULT_VALIDATION_REPORT
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--neighbors", type=int, default=NEIGHBOR_K)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = export_pack(
        args.dataset_dir,
        args.reference,
        args.validation_report,
        args.out_dir,
        k=args.neighbors,
    )
    print(f"Wrote results pack to {out_dir}")
    for child in sorted(out_dir.rglob("*")):
        if child.is_file():
            print(f"  {child.relative_to(out_dir)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
