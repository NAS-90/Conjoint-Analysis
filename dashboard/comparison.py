"""Module 5 — comparative dashboard pure helpers.

This module holds the *pure*, type-annotated functions behind the Module 5
comparative view (technical vs. customer-weighted distance). Streamlit wiring
lives in ``app.py``; everything testable lives here so it can be exercised
without importing the Streamlit app.

Key contracts (see ``../Docs/algorithm_spec.md`` §6-§7):

* The customer-weighted view re-uses the weighted distance / neighbour files
  produced by Module 4 (``distance_matrix_weighted.csv`` /
  ``nearest_neighbors_weighted.csv``) and the per-attribute importance table
  (``importance.csv``). When any of those are missing we fall back to the
  technical view and report a human-readable reason — we never crash.
* Willingness-to-pay / Part-C is display-only and must NOT feed importance,
  so nothing here folds WTP into the relative weights.
* ``weight_importance_to_relative`` is the documented fallback for datasets
  with no conjoint survey: it turns the categorical ``weight_importance``
  vocabulary into normalised relative weights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from conjoint.io import (
    ATTRIBUTE_COL,
    RELATIVE_IMPORTANCE_COL,
    read_importance,
)

PathLike = Union[str, Path]

# The categorical ``weight_importance`` vocabulary (see preprocessing.py
# ``ALLOWED_WEIGHTS``) mapped to monotonic, evenly-spaced raw scores. ``none``
# scores 0 so it drops out of the normalised weights — it marks a column that
# customers do not weight at all, mirroring the Module 4 ``default_weight=0``
# treatment of unmapped columns.
WEIGHT_IMPORTANCE_SCORES: dict[str, float] = {
    "high": 5.0,
    "medium-high": 4.0,
    "medium": 3.0,
    "low-medium": 2.0,
    "low": 1.0,
    "none": 0.0,
}

# Aliases accepted on the way in so callers can pass loosely-formatted labels.
_WEIGHT_ALIASES: dict[str, str] = {
    "": "none",
    "nan": "none",
    "n/a": "none",
    "medium high": "medium-high",
    "medium_high": "medium-high",
    "med high": "medium-high",
    "low medium": "low-medium",
    "low_medium": "low-medium",
}


# ---------------------------------------------------------------------------
# weight_importance vocabulary -> normalised relative weights
# ---------------------------------------------------------------------------
def _canonical_weight_label(label: str) -> str:
    """Normalise a raw ``weight_importance`` label to the canonical vocabulary."""
    key = str(label).strip().lower()
    key = _WEIGHT_ALIASES.get(key, key)
    if key not in WEIGHT_IMPORTANCE_SCORES:
        raise ValueError(
            f"unknown weight_importance label {label!r}; expected one of "
            f"{sorted(WEIGHT_IMPORTANCE_SCORES)}"
        )
    return key


def weight_importance_to_relative(weight_map: dict[str, str]) -> dict[str, float]:
    """Convert categorical ``weight_importance`` labels to relative weights.

    ``weight_map`` maps attribute -> categorical label drawn from the
    ``high / medium-high / medium / low-medium / low / none`` vocabulary. The
    labels are mapped to monotonic raw scores, ``none`` is dropped (it scores
    0), and the remaining scores are normalised to sum to 1.

    Returns an empty dict when every attribute is ``none`` (or the input is
    empty), since there is nothing to normalise.
    """
    raw_scores: dict[str, float] = {}
    for attribute, label in weight_map.items():
        canonical = _canonical_weight_label(label)
        score = WEIGHT_IMPORTANCE_SCORES[canonical]
        if score > 0:
            raw_scores[str(attribute)] = score

    total = sum(raw_scores.values())
    if total <= 0:
        return {}

    return {attribute: score / total for attribute, score in raw_scores.items()}


# ---------------------------------------------------------------------------
# importance.csv loading + pie chart
# ---------------------------------------------------------------------------
def load_importance(path: PathLike) -> pd.DataFrame:
    """Load ``importance.csv`` via the shared I/O contract.

    Returns the frame with the canonical importance columns
    (``attribute``, ``absolute_importance``, ``relative_importance``), with the
    attribute label trimmed.
    """
    frame = read_importance(path).copy()
    frame[ATTRIBUTE_COL] = frame[ATTRIBUTE_COL].astype(str).str.strip()
    return frame


def plot_importance_pie(importance_df: pd.DataFrame) -> go.Figure:
    """Plotly pie of ``relative_importance`` by attribute."""
    if ATTRIBUTE_COL not in importance_df.columns:
        raise ValueError(f"importance frame is missing '{ATTRIBUTE_COL}'")
    if RELATIVE_IMPORTANCE_COL not in importance_df.columns:
        raise ValueError(f"importance frame is missing '{RELATIVE_IMPORTANCE_COL}'")

    df = importance_df.copy()
    df[ATTRIBUTE_COL] = df[ATTRIBUTE_COL].astype(str).str.strip()

    fig = px.pie(
        df,
        names=ATTRIBUTE_COL,
        values=RELATIVE_IMPORTANCE_COL,
        title="Customer importance by attribute (relative)",
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(legend_title_text="attribute")
    return fig


# ---------------------------------------------------------------------------
# side-by-side technical vs customer-weighted neighbours
# ---------------------------------------------------------------------------
def _ranked_neighbors(nn_df: pd.DataFrame, product: str, k: int) -> pd.DataFrame:
    """Return the top-``k`` neighbours of ``product`` ordered by distance.

    Expects the normalised ``product / neighbor / distance`` schema produced by
    :func:`dashboard.viz.load_neighbors_table`. Adds a 1-based ``rank`` column.
    """
    required = {"product", "neighbor", "distance"}
    missing = required - set(nn_df.columns)
    if missing:
        raise ValueError(
            f"neighbours frame is missing required column(s): {sorted(missing)}"
        )

    product = str(product).strip()
    sub = nn_df.copy()
    sub["product"] = sub["product"].astype(str).str.strip()
    sub["neighbor"] = sub["neighbor"].astype(str).str.strip()
    sub = sub[sub["product"] == product].sort_values("distance").head(k)
    sub = sub.reset_index(drop=True)
    sub.insert(0, "rank", range(1, len(sub) + 1))
    return sub[["rank", "neighbor", "distance"]]


def build_side_by_side_neighbors(
    nn_technical: pd.DataFrame,
    nn_weighted: pd.DataFrame,
    product: str,
    k: int = 5,
) -> pd.DataFrame:
    """Build a rank-aligned technical-vs-weighted neighbour comparison table.

    For ``product`` the two views are each reduced to their top-``k`` neighbours
    (ordered by ascending distance) and joined on rank. The two views may rank
    different products at the same position, so the result keeps both the
    technical and weighted neighbour name/distance side by side. Ranks present
    in only one view are kept with NaN/empty values on the other side.

    Output columns:
    ``rank``, ``technical_neighbor``, ``technical_distance``,
    ``weighted_neighbor``, ``weighted_distance``.
    """
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")

    tech = _ranked_neighbors(nn_technical, product, k).rename(
        columns={"neighbor": "technical_neighbor", "distance": "technical_distance"}
    )
    weighted = _ranked_neighbors(nn_weighted, product, k).rename(
        columns={"neighbor": "weighted_neighbor", "distance": "weighted_distance"}
    )

    merged = tech.merge(weighted, on="rank", how="outer").sort_values("rank")
    merged = merged.reset_index(drop=True)

    merged["technical_neighbor"] = merged["technical_neighbor"].fillna("")
    merged["weighted_neighbor"] = merged["weighted_neighbor"].fillna("")

    return merged[
        [
            "rank",
            "technical_neighbor",
            "technical_distance",
            "weighted_neighbor",
            "weighted_distance",
        ]
    ]


# ---------------------------------------------------------------------------
# view resolution (technical vs customer-weighted) with graceful fallback
# ---------------------------------------------------------------------------
def resolve_view(paths: dict[str, Path], view: str) -> dict[str, object]:
    """Resolve which distance/neighbour artifacts a given ``view`` should use.

    ``paths`` is a :func:`dashboard.viz.dataset_paths` registry. ``view`` is
    one of ``"technical"`` or ``"weighted"``.

    For the technical view we always return the technical ``dm`` / ``nn`` paths.
    For the weighted view we require the weighted distance matrix, the weighted
    neighbours table *and* ``importance.csv``; if any are missing we gracefully
    fall back to the technical artifacts and surface a human-readable ``reason``.

    Returns a dict with:
    ``view`` (the view actually applied),
    ``requested`` (the view that was asked for),
    ``dm`` / ``nn`` (paths to use),
    ``importance`` (path or ``None``),
    ``fell_back`` (bool),
    ``reason`` (str or ``None``).
    """
    if view not in ("technical", "weighted"):
        raise ValueError(
            f"view must be 'technical' or 'weighted', got {view!r}"
        )

    technical = {
        "view": "technical",
        "requested": view,
        "dm": paths["dm"],
        "nn": paths["nn"],
        "importance": paths["importance"] if Path(paths["importance"]).exists() else None,
        "fell_back": False,
        "reason": None,
    }

    if view == "technical":
        return technical

    missing = [
        key
        for key in ("dm_weighted", "nn_weighted", "importance")
        if not Path(paths[key]).exists()
    ]
    if missing:
        reason = (
            "Customer-weighted view unavailable (missing: "
            + ", ".join(Path(paths[key]).name for key in missing)
            + "). Falling back to the technical view. Run Module 4's weighted "
            "distance and the conjoint importance step to enable it."
        )
        fallback = dict(technical)
        fallback["requested"] = "weighted"
        fallback["fell_back"] = True
        fallback["reason"] = reason
        return fallback

    return {
        "view": "weighted",
        "requested": "weighted",
        "dm": paths["dm_weighted"],
        "nn": paths["nn_weighted"],
        "importance": paths["importance"],
        "fell_back": False,
        "reason": None,
    }
