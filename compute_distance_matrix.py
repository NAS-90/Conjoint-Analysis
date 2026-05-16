from __future__ import annotations

import argparse
import os
import re
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# =========================
#           CONFIG
# =========================
FILE_PATH = "Database_Distance Analysis.xlsx"
DATA_SHEET = "Edited"
PRODUCT_COL = "product"

INPUT_CSV = "preprocessed_output.csv"
OUTPUT_DISTANCE_CSV = "distance_matrix.csv"
OUTPUT_NEIGHBORS_CSV = "nearest_neighbors.csv"
OUTPUT_SUMMARY_TXT = "distance_summary.txt"

TOP_K_NEIGHBORS = 5
FLOAT_DTYPE = "float64"

SCALE_ALL_FEATURES = True

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

    s = re.sub(r"^[\u2022\u00b7\*\-\+]+\s*", "", s)

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


def compute_euclidean_distance_matrix(X: np.ndarray) -> np.ndarray:
    # D^2 = ||x_i||^2 + ||x_j||^2 - 2 x_i·x_j
    sq = np.sum(X * X, axis=1, keepdims=True)
    D2 = sq + sq.T - 2.0 * (X @ X.T)
    np.maximum(D2, 0.0, out=D2)
    D = np.sqrt(D2)
    np.fill_diagonal(D, 0.0)
    return D


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

parser = argparse.ArgumentParser()
parser.add_argument("--excel", type=str, default=FILE_PATH)
parser.add_argument("--product-col", dest="product_col", type=str, default=PRODUCT_COL,
                    help="Column in the Edited sheet to use as the product/row label.")
args, _ = parser.parse_known_args()

FILE_PATH = args.excel
PRODUCT_COL = args.product_col

# =========================
#            MAIN
# =========================
def main():
    if not os.path.exists(INPUT_CSV):
        raise FileNotFoundError(f"Missing {INPUT_CSV}")
    if not os.path.exists(FILE_PATH):
        raise FileNotFoundError(f"Missing {FILE_PATH}")

    df_raw = pd.read_csv(INPUT_CSV)
    n_rows = len(df_raw)

    product_names = load_product_names(FILE_PATH, DATA_SHEET, PRODUCT_COL, n_rows)

    X_df = coerce_dataframe_to_numeric(df_raw).astype(FLOAT_DTYPE)

    if SCALE_ALL_FEATURES:
        scaler = StandardScaler(with_mean=True, with_std=True)
        X = scaler.fit_transform(X_df.to_numpy(dtype=FLOAT_DTYPE, copy=True))
    else:
        X = X_df.to_numpy(dtype=FLOAT_DTYPE, copy=True)

    D = compute_euclidean_distance_matrix(X)
    sanity_checks(D)

    dist_df = pd.DataFrame(D, index=product_names, columns=product_names)
    dist_df.to_csv(OUTPUT_DISTANCE_CSV, index=True)

    neighbors_df = build_neighbors_table(dist_df, TOP_K_NEIGHBORS)
    neighbors_df.to_csv(OUTPUT_NEIGHBORS_CSV, index=False)

    write_distance_summary(dist_df, neighbors_df, OUTPUT_SUMMARY_TXT)

    print("Task 3 Complete.")
    print(f"Input: {INPUT_CSV} (n={X.shape[0]}, d={X.shape[1]})")
    print(f"SCALE_ALL_FEATURES: {SCALE_ALL_FEATURES}")
    print(f"Distance matrix: {OUTPUT_DISTANCE_CSV} (shape={dist_df.shape})")
    print(f"Nearest neighbors: {OUTPUT_NEIGHBORS_CSV} (top_k={TOP_K_NEIGHBORS})")
    print(f"Summary report: {OUTPUT_SUMMARY_TXT}")


if __name__ == "__main__":
    main()
