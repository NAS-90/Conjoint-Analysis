"""Module 4 — distance matrix (technical + customer-weighted).

This module turns the preprocessed feature matrix (``preprocessed_output.csv``)
into a product-by-product distance matrix and a nearest-neighbour table.

Two modes are supported:

* ``technical``  — z-score every feature column (``StandardScaler``) then plain
  Euclidean distance.  This is the historical behaviour and is preserved
  byte-for-byte by the refactor.
* ``weighted``   — additionally re-scale every z-scored column ``j`` belonging to
  conjoint attribute ``a`` by ``√(RI_a / m_a)`` before computing the Euclidean
  distance, where ``RI_a`` is the relative importance of attribute ``a`` and
  ``m_a`` the number of preprocessed columns that attribute expands into
  (``algorithm_spec.md`` §6).

Weighted-Euclidean convention
-----------------------------
Per ``algorithm_spec.md`` §6, each scaled value in column ``j`` is multiplied by
``√(RI_a / m_a)``.  The squared per-column contribution to the distance is
therefore ``(RI_a / m_a) · Δ_j²``.  We expose this as a per-column **weight
vector** ``w_j = RI_a / m_a`` and define::

    weighted_distance_matrix(X, w) = √( Σ_j w_j · (x_ij − x_kj)² )

which is exactly the spec's ``d_w(A, B) = √( Σ_j w_j (a_j − b_j)² )`` (line 87).
The per-column multiplier applied to the scaled value is ``√w_j``.

Importing this module has NO side effects; all CLI handling lives in
:func:`main` / :func:`parse_args`.
"""

from __future__ import annotations

import argparse
import os
import re
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# =========================
#           CONFIG
# =========================
FILE_PATH = "Database_Distance Analysis.xlsx"
DATA_SHEET = "Edited"
# Different datasets label their rows differently (tractors use "product",
# smartphones use "model"). Auto-detect by trying these in order; override
# with --product-col.
PRODUCT_COL_CANDIDATES = ["product_id", "product", "model", "brand", "name"]

INPUT_CSV = "preprocessed_output.csv"
OUTPUT_DISTANCE_CSV = "distance_matrix.csv"
OUTPUT_NEIGHBORS_CSV = "nearest_neighbors.csv"
OUTPUT_SUMMARY_TXT = "distance_summary.txt"

# Weighted-mode outputs (kept separate so technical files are never clobbered).
OUTPUT_DISTANCE_CSV_WEIGHTED = "distance_matrix_weighted.csv"
OUTPUT_NEIGHBORS_CSV_WEIGHTED = "nearest_neighbors_weighted.csv"

TOP_K_NEIGHBORS = 5
FLOAT_DTYPE = "float64"

SCALE_ALL_FEATURES = True

# Fallback weight for columns that are NOT covered by the attribute map (e.g.
# ``price`` with conjoint_role=skip, or any metric column the conjoint never
# rated). This is the per-column weight ``w_j`` (entering as ``√w_j`` on the
# scaled value), so the default of 0.0 means "carry no conjoint signal":
# unmapped columns drop out of the *customer-weighted* distance entirely. That
# matches the dashboard's intent — the weighted view answers "how different are
# these products on the dimensions customers said they care about" — while the
# technical view still uses every column. Override with ``--unmapped-weight``;
# e.g. pass the mean of the conjoint per-column weights to keep unmapped columns
# at "average" influence. For the tractor reference case every distance column
# is a conjoint attribute, so the fallback is never exercised there.
DEFAULT_UNMAPPED_WEIGHT = 0.0

_TRUE_SET = {"true", "1", "yes", "y", "available"}
_FALSE_SET = {"false", "0", "no", "n", "not available", "nan", ""}


# =========================
#           HELPERS
# =========================
def _clean_bool_like_to_int(x):

    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    if isinstance(x, (bool, np.bool_)):
        return int(x)

    s = str(x).strip().lower()

    s = re.sub(r"^[•·\*\-\+]+\s*", "", s)

    if s in _TRUE_SET:
        return 1
    if s in _FALSE_SET:
        return 0
    if s.startswith("true"):
        return 1
    if s.startswith("false"):
        return 0
    return None


def coerce_dataframe_to_numeric(df: pd.DataFrame) -> pd.DataFrame:

    df2 = df.copy()

    bool_cols = df2.select_dtypes(include=["bool"]).columns
    if len(bool_cols) > 0:
        df2[bool_cols] = df2[bool_cols].astype(int)

    obj_cols = df2.select_dtypes(include=["object"]).columns
    for col in obj_cols:
        mapped = df2[col].map(_clean_bool_like_to_int)
        non_null = df2[col].notna().sum()
        recognized = mapped.notna().sum()

        if non_null > 0 and recognized / non_null >= 0.7:
            df2[col] = mapped.fillna(0).astype(int)
        else:
            df2[col] = pd.to_numeric(df2[col], errors="coerce")

    non_numeric = [c for c in df2.columns if not pd.api.types.is_numeric_dtype(df2[c])]
    if non_numeric:
        raise ValueError(f"Non-numeric columns remain: {non_numeric}")

    if df2.isna().any().any():
        df2 = df2.fillna(df2.mean(numeric_only=True))

    return df2


def scale_matrix(X: np.ndarray) -> np.ndarray:
    """Z-score every column (mean 0, unit variance) via ``StandardScaler``.

    This is the exact transform used by the original technical pipeline; it is
    factored out so both modes share one implementation.
    """
    scaler = StandardScaler(with_mean=True, with_std=True)
    return scaler.fit_transform(np.asarray(X, dtype=FLOAT_DTYPE))


def compute_euclidean_distance_matrix(X: np.ndarray) -> np.ndarray:
    # D^2 = ||x_i||^2 + ||x_j||^2 - 2 x_i·x_j
    sq = np.sum(X * X, axis=1, keepdims=True)
    D2 = sq + sq.T - 2.0 * (X @ X.T)
    np.maximum(D2, 0.0, out=D2)
    D = np.sqrt(D2)
    np.fill_diagonal(D, 0.0)
    return D


def build_weight_vector(
    columns: Sequence[str],
    importance: pd.DataFrame,
    attribute_map: Mapping[str, Mapping[str, object]],
    *,
    default_weight: float = DEFAULT_UNMAPPED_WEIGHT,
) -> np.ndarray:
    """Build the per-column weight vector ``w_j`` for the weighted distance.

    For a preprocessed column ``j`` belonging to attribute ``a`` (per the
    attribute map's ``columns`` lists) the weight is ``w_j = RI_a / m_a`` where
    ``RI_a`` is the relative importance of ``a`` and ``m_a`` its column count.
    Columns not covered by the map receive ``default_weight``.

    The returned vector is meant to be consumed by
    :func:`weighted_distance_matrix`, i.e. each scaled value is multiplied by
    ``√w_j`` and the squared contribution is ``w_j · Δ_j²``.

    Parameters
    ----------
    columns:
        Preprocessed feature columns, in matrix order.
    importance:
        ``importance.csv`` frame with ``attribute`` and ``relative_importance``
        columns (see :data:`conjoint.io.IMPORTANCE_COLUMNS`).
    attribute_map:
        ``attribute_column_map.json`` mapping attribute -> ``{"columns": [...],
        "m_a": int, ...}``.
    default_weight:
        Weight assigned to columns absent from the map. Must be non-negative.
    """
    if default_weight < 0:
        raise ValueError(f"default_weight must be non-negative, got {default_weight}")

    ri_by_attribute = _relative_importance_lookup(importance)

    # Map every mapped preprocessed column -> its per-column weight RI_a / m_a.
    weight_by_column: dict[str, float] = {}
    for attribute, entry in attribute_map.items():
        attr_columns = entry.get("columns", []) if isinstance(entry, Mapping) else []
        m_a = _attribute_column_count(attribute, entry, attr_columns)
        if attribute not in ri_by_attribute:
            raise ValueError(
                f"attribute '{attribute}' from the attribute map is missing from "
                f"importance.csv (have: {sorted(ri_by_attribute)})"
            )
        per_column_weight = float(ri_by_attribute[attribute]) / m_a
        for col in attr_columns:
            weight_by_column[str(col)] = per_column_weight

    weights = np.array(
        [weight_by_column.get(str(col), float(default_weight)) for col in columns],
        dtype=FLOAT_DTYPE,
    )
    return weights


def _relative_importance_lookup(importance: pd.DataFrame) -> dict[str, float]:
    """Extract ``{attribute: relative_importance}`` from an importance frame."""
    required = {"attribute", "relative_importance"}
    missing = required - set(importance.columns)
    if missing:
        raise ValueError(
            f"importance frame is missing required column(s): {sorted(missing)}"
        )
    return {
        str(attr): float(ri)
        for attr, ri in zip(
            importance["attribute"], importance["relative_importance"]
        )
    }


def _attribute_column_count(
    attribute: str, entry: Mapping[str, object], attr_columns: Sequence[object]
) -> int:
    """Resolve ``m_a`` for an attribute, validating it against its columns."""
    m_a = entry.get("m_a", len(attr_columns)) if isinstance(entry, Mapping) else 0
    m_a = int(m_a)
    if m_a <= 0 or len(attr_columns) == 0:
        raise ValueError(
            f"attribute '{attribute}' has no preprocessed columns (m_a={m_a})"
        )
    if m_a != len(attr_columns):
        raise ValueError(
            f"attribute '{attribute}' m_a={m_a} disagrees with its column count "
            f"{len(attr_columns)}"
        )
    return m_a


def weighted_distance_matrix(X_scaled: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted Euclidean distance ``√( Σ_j w_j (x_ij − x_kj)² )``.

    Each already-scaled column ``j`` is multiplied by ``√w_j`` and a plain
    Euclidean distance is taken, so the squared per-column contribution is
    ``w_j · Δ_j²`` — the convention from ``algorithm_spec.md`` §6.
    """
    X_scaled = np.asarray(X_scaled, dtype=FLOAT_DTYPE)
    weights = np.asarray(weights, dtype=FLOAT_DTYPE)
    if weights.ndim != 1 or weights.shape[0] != X_scaled.shape[1]:
        raise ValueError(
            f"weights length {weights.shape} must match feature count "
            f"{X_scaled.shape[1]}"
        )
    if np.any(weights < 0):
        raise ValueError("weights must be non-negative")
    X_weighted = X_scaled * np.sqrt(weights)
    return compute_euclidean_distance_matrix(X_weighted)


def make_unique_names(names: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        base = (n or "").strip()
        if base == "" or base.lower() == "nan":
            base = "UNKNOWN"

        if base not in counts:
            counts[base] = 0
            out.append(base)
        else:
            counts[base] += 1
            out.append(f"{base}__{counts[base]}")
    return out


def resolve_product_col(excel_path: str, sheet: str, requested: str | None) -> str:
    """Resolve the product-label column, validating against the sheet header.

    If `requested` is given it must exist in the sheet; otherwise auto-detect
    using PRODUCT_COL_CANDIDATES. Both paths fail with a clear, actionable error.
    """
    columns = pd.read_excel(excel_path, sheet_name=sheet, nrows=0).columns.tolist()

    if requested is not None:
        if requested in columns:
            return requested
        raise ValueError(
            f"--product-col '{requested}' not found in sheet '{sheet}'. "
            f"Available columns: {columns}."
        )

    for candidate in PRODUCT_COL_CANDIDATES:
        if candidate in columns:
            return candidate
    raise ValueError(
        "Could not infer the product label column. Expected one of: "
        f"{PRODUCT_COL_CANDIDATES}. Available columns in sheet '{sheet}': {columns}. "
        "Pass --product-col <name> to specify it explicitly."
    )


def load_product_names(excel_path: str, sheet: str, product_col: str, n_rows: int) -> list[str]:
    df = pd.read_excel(excel_path, sheet_name=sheet, usecols=[product_col])
    names = df[product_col].astype(str).tolist()

    if len(names) < n_rows:
        names += [None] * (n_rows - len(names))
    if len(names) > n_rows:
        names = names[:n_rows]

    names = make_unique_names(names)

    for i in range(len(names)):
        if names[i] == "UNKNOWN":
            names[i] = f"row_{i}"
    return names


def build_neighbors_table(dist_df: pd.DataFrame, k: int) -> pd.DataFrame:
    ids = dist_df.index.tolist()
    rows = []
    for i in ids:
        s = dist_df.loc[i].sort_values()
        neighbors = s.iloc[1: 1 + k]
        for r, (j, d) in enumerate(neighbors.items(), start=1):
            rows.append({"product": i, "neighbor_rank": r, "neighbor": j, "distance": float(d)})
    return pd.DataFrame(rows)


def sanity_checks(D: np.ndarray):
    if not np.all(np.isfinite(D)):
        raise ValueError("Distance matrix contains NaN or inf.")
    if np.min(D) < -1e-10:
        raise ValueError(f"Distance matrix has negative values (min={np.min(D)}).")
    if not np.allclose(D, D.T, atol=1e-8):
        raise ValueError("Distance matrix is not symmetric.")
    if not np.allclose(np.diag(D), 0.0, atol=1e-12):
        raise ValueError("Distance matrix diagonal is not all zeros.")


def write_distance_summary(dist_df: pd.DataFrame, neighbors_df: pd.DataFrame, path: str):
    D = dist_df.to_numpy(copy=False)
    mask = ~np.eye(D.shape[0], dtype=bool)
    off = D[mask]

    lines = []
    lines.append("=== Distance Matrix Summary (off-diagonal) ===")
    lines.append(f"n_products: {D.shape[0]}")
    lines.append(f"min:   {off.min():.6f}")
    lines.append(f"mean:  {off.mean():.6f}")
    lines.append(f"median:{np.median(off):.6f}")
    lines.append(f"max:   {off.max():.6f}")
    lines.append("")
    lines.append("=== Nearest Neighbor Distance Summary (rank=1) ===")
    first_nn = neighbors_df[neighbors_df["neighbor_rank"] == 1]["distance"].to_numpy()
    lines.append(f"min:   {first_nn.min():.6f}")
    lines.append(f"mean:  {first_nn.mean():.6f}")
    lines.append(f"median:{np.median(first_nn):.6f}")
    lines.append(f"max:   {first_nn.max():.6f}")
    lines.append("")
    lines.append("Note: SCALE_ALL_FEATURES is enabled -> all columns standardized before Euclidean distance.")
    lines.append("If you see distance=0 between different products, their preprocessed feature vectors are identical.")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# =========================
#            CLI
# =========================
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments. Pure: no I/O, no global mutation."""
    parser = argparse.ArgumentParser(
        description="Compute a technical or customer-weighted product distance matrix.",
    )
    parser.add_argument("--excel", type=str, default=FILE_PATH)
    parser.add_argument(
        "--product-col",
        dest="product_col",
        type=str,
        default=None,
        help="Column in the Edited sheet to use as the product/row label. "
        f"Defaults to auto-detecting one of {PRODUCT_COL_CANDIDATES}.",
    )
    parser.add_argument(
        "--input-csv",
        dest="input_csv",
        type=str,
        default=INPUT_CSV,
        help=f"Preprocessed feature matrix CSV (default: {INPUT_CSV}).",
    )
    parser.add_argument(
        "--mode",
        choices=("technical", "weighted"),
        default="technical",
        help="technical: z-score + Euclidean (default). weighted: additionally "
        "scale each column by sqrt(RI_a / m_a) before Euclidean.",
    )
    parser.add_argument(
        "--importance",
        type=str,
        default=None,
        help="importance.csv (attribute, absolute_importance, relative_importance). "
        "Required in weighted mode.",
    )
    parser.add_argument(
        "--attribute-map",
        dest="attribute_map",
        type=str,
        default=None,
        help="attribute_column_map.json mapping attributes to preprocessed "
        "columns. Required in weighted mode.",
    )
    parser.add_argument(
        "--unmapped-weight",
        dest="unmapped_weight",
        type=float,
        default=DEFAULT_UNMAPPED_WEIGHT,
        help="Per-column weight w_j for columns absent from the attribute map "
        f"(weighted mode only; default: {DEFAULT_UNMAPPED_WEIGHT}, i.e. unmapped "
        "columns are excluded from the customer-weighted distance).",
    )
    return parser.parse_args(argv)


def _prepare_scaled_matrix(input_csv: str) -> tuple[np.ndarray, list[str], int]:
    """Load the preprocessed CSV, coerce to numeric and z-score it."""
    df_raw = pd.read_csv(input_csv)
    n_rows = len(df_raw)
    feature_columns = list(df_raw.columns)

    X_df = coerce_dataframe_to_numeric(df_raw).astype(FLOAT_DTYPE)
    X_values = X_df.to_numpy(dtype=FLOAT_DTYPE, copy=True)

    if SCALE_ALL_FEATURES:
        X_scaled = scale_matrix(X_values)
    else:
        X_scaled = X_values
    return X_scaled, feature_columns, n_rows


# =========================
#            MAIN
# =========================
def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    excel_path = args.excel
    input_csv = args.input_csv

    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"Missing {input_csv}")
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Missing {excel_path}")

    X_scaled, feature_columns, n_rows = _prepare_scaled_matrix(input_csv)

    product_col = resolve_product_col(excel_path, DATA_SHEET, args.product_col)
    product_names = load_product_names(excel_path, DATA_SHEET, product_col, n_rows)

    if args.mode == "weighted":
        if args.importance is None or args.attribute_map is None:
            raise ValueError(
                "weighted mode requires --importance and --attribute-map."
            )
        # Imported lazily so importing this module stays dependency-light.
        from conjoint.io import read_attribute_map, read_importance

        importance = read_importance(args.importance)
        attribute_map = read_attribute_map(args.attribute_map)
        weights = build_weight_vector(
            feature_columns,
            importance,
            attribute_map,
            default_weight=args.unmapped_weight,
        )
        D = weighted_distance_matrix(X_scaled, weights)
        distance_csv = OUTPUT_DISTANCE_CSV_WEIGHTED
        neighbors_csv = OUTPUT_NEIGHBORS_CSV_WEIGHTED
    else:
        D = compute_euclidean_distance_matrix(X_scaled)
        distance_csv = OUTPUT_DISTANCE_CSV
        neighbors_csv = OUTPUT_NEIGHBORS_CSV

    sanity_checks(D)

    dist_df = pd.DataFrame(D, index=product_names, columns=product_names)
    dist_df.to_csv(distance_csv, index=True)

    neighbors_df = build_neighbors_table(dist_df, TOP_K_NEIGHBORS)
    neighbors_df.to_csv(neighbors_csv, index=False)

    if args.mode == "technical":
        write_distance_summary(dist_df, neighbors_df, OUTPUT_SUMMARY_TXT)

    print(f"Task 3 Complete. (mode={args.mode})")
    print(f"Input: {input_csv} (n={X_scaled.shape[0]}, d={X_scaled.shape[1]})")
    print(f"Product label column: {product_col}")
    print(f"SCALE_ALL_FEATURES: {SCALE_ALL_FEATURES}")
    print(f"Distance matrix: {distance_csv} (shape={dist_df.shape})")
    print(f"Nearest neighbors: {neighbors_csv} (top_k={TOP_K_NEIGHBORS})")
    if args.mode == "technical":
        print(f"Summary report: {OUTPUT_SUMMARY_TXT}")


if __name__ == "__main__":
    main()
