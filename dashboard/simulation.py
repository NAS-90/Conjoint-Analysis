"""Removal-simulation helpers used by the dashboard.

Two complementary views are offered:

* :func:`simulate_removal` — the legacy "who replaces whom on the
  distance map" question: for every removed product, find the nearest
  surviving product, report distances + flag market gaps.
* :func:`simulate_share_transfer` — the new ACBC-flavoured view:
  given a utilities frame + product spec table, compute share-of-
  preference before and after removal so the dashboard can show
  *who absorbed the removed share* and how the histogram of pairwise
  distances changes.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Legacy: nearest-neighbour substitute table (Task 3 historical contract)
# ---------------------------------------------------------------------------
def simulate_removal(df, dist_matrix, products_to_remove, threshold=None):
    """Distance-based "find a substitute" simulation.

    For each removed product, look at the distance row, exclude every
    other removed product + itself, and pick the closest remaining
    product as the substitute. Returns a dict with the substitutes,
    summary distances and (optional) gap list (products whose nearest
    substitute exceeds ``threshold``).
    """
    if not products_to_remove:
        return {"error": "No products selected."}

    substitutes = {}
    substitute_distances = []
    gaps = []

    for product in products_to_remove:
        if product not in df.index:
            continue

        idx = df.index.get_loc(product)
        distances = dist_matrix[idx]
        candidate_indices = [
            i for i, name in enumerate(df.index)
            if name not in products_to_remove and name != product
        ]
        if not candidate_indices:
            continue
        candidate_distances = distances[candidate_indices]
        best_idx = candidate_indices[np.argmin(candidate_distances)]
        best_product = df.index[best_idx]
        best_distance = distances[best_idx]

        substitutes[product] = {
            "substitute": best_product,
            "distance": float(best_distance),
        }
        substitute_distances.append(best_distance)
        if threshold is not None and best_distance > threshold:
            gaps.append(product)

    if not substitute_distances:
        return {"error": "No substitutes found."}
    return {
        "substitutes": substitutes,
        "mean_dist": float(np.mean(substitute_distances)),
        "max_dist": float(np.max(substitute_distances)),
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Before/after distance histogram
# ---------------------------------------------------------------------------
def distance_histogram_data(
    dist_matrix: np.ndarray, products: list[str], removed: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(distances_before, distances_after)`` upper-triangle distances.

    ``products`` is the row/column label order of ``dist_matrix``; we
    drop the rows + columns of every removed product to compute the
    after-state.
    """
    upper = np.triu_indices(dist_matrix.shape[0], k=1)
    before = dist_matrix[upper]

    if not removed:
        return before, before
    kept_indices = [i for i, name in enumerate(products) if name not in removed]
    if len(kept_indices) <= 1:
        return before, np.array([], dtype=float)
    sub = dist_matrix[np.ix_(kept_indices, kept_indices)]
    after = sub[np.triu_indices(sub.shape[0], k=1)]
    return before, after


# ---------------------------------------------------------------------------
# Share-of-preference: who absorbed the removed share?
# ---------------------------------------------------------------------------
def share_transfer_table(
    utilities_frame: pd.DataFrame,
    products: Mapping[str, Mapping[str, str]],
    to_remove: list[str],
    level_map: Mapping[str, list[str]],
    *,
    alpha: float = 1.0,
) -> pd.DataFrame:
    """Wrap :func:`conjoint.acbc.simulation.removal_impact` for the dashboard.

    ``utilities_frame`` is the wide per-respondent utilities table
    written by :func:`conjoint.estimate.estimate_utilities` /
    :func:`conjoint.acbc.estimate.hb_to_utilities`. ``products`` is the
    dashboard's product->attribute->level lookup. Returns the
    ``transfer`` DataFrame with one row per product (before / after
    share and delta).
    """
    from conjoint.acbc import simulation as acbc_simulation

    utilities_by_respondent = acbc_simulation.utilities_from_frame(
        utilities_frame, level_map
    )
    impact = acbc_simulation.removal_impact(
        utilities_by_respondent, products, to_remove, model="logit", alpha=alpha
    )
    return impact.transfer
