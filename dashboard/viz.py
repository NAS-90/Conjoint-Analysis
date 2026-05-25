from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import plotly.express as px


# =========================
# Helpers / Loading
# =========================
def _clean_str(x) -> str:
    return str(x).strip()


def dataset_paths(outputs_dir: str | Path, dataset: str) -> dict[str, Path]:
    base = Path(outputs_dir) / dataset
    return {
        "base": base,
        "pre": base / "preprocessed_output.csv",
        "dm": base / "distance_matrix.csv",
        "nn": base / "nearest_neighbors.csv",
        "dm_weighted": base / "distance_matrix_weighted.csv",
        "nn_weighted": base / "nearest_neighbors_weighted.csv",
        "importance": base / "importance.csv",
        "summary": base / "distance_summary.txt",
        "dashboard_inputs": base / "dashboard_inputs.csv",
        "fig_neighbor": base / "neighbor_bar.html",
        "fig_hist": base / "distance_hist.html",
        "fig_pca_2d": base / "pca_embedding_2d.html",
        "fig_pca_3d": base / "pca_embedding_3d.html",
    }


def _numeric_view(df: pd.DataFrame) -> pd.DataFrame:
    """Numeric columns of ``df``, with one-hot ``bool`` columns cast to ``int8``.

    The universal preprocessor encodes nominal/text features as one-hot ``bool``
    columns (``pandas.get_dummies``). Those are perfectly valid numeric features
    for PCA / distance, so we include them here — otherwise an all-categorical
    dataset (e.g. the conjoint demo) would look like it has *no* numeric columns.
    """
    num = df.select_dtypes(include=[np.number]).copy()
    bool_cols = df.select_dtypes(include=["bool"])
    for col in bool_cols.columns:
        num[col] = bool_cols[col].astype("int8")
    # Preserve original column order.
    ordered = [c for c in df.columns if c in num.columns]
    return num[ordered]


def load_preprocessed_numeric(
    path: str | Path,
    selected_features: list[str] | None = None,
) -> pd.DataFrame:
    df = pd.read_csv(path)
    num = _numeric_view(df)

    if num.shape[1] == 0:
        raise ValueError(f"No numeric columns found in {path}. PCA requires numeric features.")

    if selected_features is not None and len(selected_features) > 0:
        selected_features_clean = [_clean_str(c) for c in selected_features]
        available_cols = [_clean_str(c) for c in num.columns]

        missing = [c for c in selected_features_clean if c not in available_cols]
        if missing:
            raise ValueError(
                f"Selected features not found in numeric columns: {missing}. "
                f"Available numeric columns: {available_cols}"
            )

        num = num[selected_features_clean].copy()

    if num.shape[1] == 0:
        raise ValueError("No numeric features available after applying selected_features.")

    if num.isna().any().any():
        num = num.fillna(num.mean(numeric_only=True))

    return num


def get_available_numeric_features(path: str | Path) -> list[str]:
    df = pd.read_csv(path)
    num = _numeric_view(df)
    return [str(c).strip() for c in num.columns]


def load_distance_matrix(path: str | Path) -> pd.DataFrame:
    dm = pd.read_csv(path, index_col=0)
    dm.index = dm.index.astype(str).str.strip()
    dm.columns = dm.columns.astype(str).str.strip()
    dm = dm.apply(pd.to_numeric, errors="coerce")

    if dm.isna().any().any():
        dm = dm.fillna(dm.mean(numeric_only=True))

    return dm


def load_neighbors_table(path: str | Path) -> pd.DataFrame:
    nn = pd.read_csv(path)

    expected = {"product", "neighbor", "distance"}
    if expected.issubset(set(nn.columns)):
        nn["product"] = nn["product"].astype(str).str.strip()
        nn["neighbor"] = nn["neighbor"].astype(str).str.strip()
        nn["distance"] = pd.to_numeric(nn["distance"], errors="coerce")
        return nn[["product", "neighbor", "distance"]]

    nn2 = nn.copy()
    nn2.iloc[:, 0] = nn2.iloc[:, 0].astype(str).str.strip()
    nn2.iloc[:, 2] = nn2.iloc[:, 2].astype(str).str.strip()
    nn2.iloc[:, -1] = pd.to_numeric(nn2.iloc[:, -1], errors="coerce")
    nn2 = nn2.rename(
        columns={
            nn2.columns[0]: "product",
            nn2.columns[2]: "neighbor",
            nn2.columns[-1]: "distance",
        }
    )
    return nn2[["product", "neighbor", "distance"]]


# =========================
# Visualizations
# =========================
def neighbors_for_product(nn_df: pd.DataFrame, product: str, k: int = 10) -> pd.DataFrame:
    product = _clean_str(product)
    sub = nn_df[nn_df["product"] == product].sort_values("distance").head(k).copy()
    return sub[["neighbor", "distance"]]


def plot_neighbor_bar(neighbors_df: pd.DataFrame, selected_product: str):
    fig = px.bar(
        neighbors_df.sort_values("distance", ascending=True),
        x="distance",
        y="neighbor",
        orientation="h",
        title=f"Nearest neighbors of selected product: {selected_product}"
    )
    fig.update_layout(xaxis_title="distance", yaxis_title="neighbor")
    return fig


def plot_distance_histogram(dm: pd.DataFrame, nbins: int = 40):
    arr = dm.to_numpy()
    n = arr.shape[0]
    tri = arr[np.triu_indices(n, k=1)]
    tri = tri[~np.isnan(tri)]

    fig = px.histogram(
        x=tri,
        nbins=nbins,
        title="Distance distribution (all product pairs)"
    )
    fig.update_layout(xaxis_title="distance", yaxis_title="count")
    return fig


def compute_pca_embedding(
    preprocessed_numeric: pd.DataFrame,
    product_keys: list[str],
    n_components: int = 2,
) -> pd.DataFrame:
    product_keys = [_clean_str(p) for p in product_keys]

    if n_components not in (2, 3):
        raise ValueError("n_components must be 2 or 3.")

    if len(product_keys) != len(preprocessed_numeric):
        raise ValueError(
            "Row count mismatch: preprocessed_numeric and product_keys must have the same length. "
            f"Got {len(preprocessed_numeric)} rows and {len(product_keys)} product keys."
        )

    if preprocessed_numeric.shape[1] < n_components:
        raise ValueError(
            f"Not enough selected features for PCA with n_components={n_components}. "
            f"Need at least {n_components}, got {preprocessed_numeric.shape[1]}."
        )

    X = preprocessed_numeric.copy()

    if X.isna().any().any():
        X = X.fillna(X.mean(numeric_only=True))

    nunique = X.nunique(dropna=False)
    keep_cols = nunique[nunique > 1].index.tolist()
    X = X[keep_cols]

    if X.shape[1] < n_components:
        raise ValueError(
            f"Not enough non-constant features for PCA with n_components={n_components}. "
            f"Need at least {n_components}, got {X.shape[1]}."
        )

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    pca = PCA(n_components=n_components, random_state=42)
    emb = pca.fit_transform(X_scaled)

    data = {
        "product": product_keys,
        "embedding_x": emb[:, 0],
        "embedding_y": emb[:, 1],
    }
    if n_components == 3:
        data["embedding_z"] = emb[:, 2]

    out = pd.DataFrame(data)
    out.attrs["explained_variance_ratio"] = pca.explained_variance_ratio_.tolist()
    return out


def _add_roles(embedding_df: pd.DataFrame, selected: str, neighbors: list[str]) -> pd.DataFrame:
    df = embedding_df.copy()
    df["product"] = df["product"].astype(str).str.strip()

    selected = _clean_str(selected)
    neighbors = [_clean_str(x) for x in neighbors]

    df["role"] = "other"
    df.loc[df["product"] == selected, "role"] = "selected"
    df.loc[df["product"].isin(neighbors), "role"] = "neighbor"

    return df

def _apply_small_jitter(df: pd.DataFrame, cols: list[str], seed: int = 42) -> pd.DataFrame:
    out = df.copy()
    rng = np.random.default_rng(seed)

    for c in cols:
        if c not in out.columns:
            continue

        values = out[c].to_numpy(dtype=float)
        if len(np.unique(values)) == len(values):
            continue

        vmin, vmax = np.nanmin(values), np.nanmax(values)
        span = vmax - vmin
        eps = 0.01 * span if span > 0 else 0.05
        out[c] = values + rng.normal(0, eps, size=len(values))

    return out


def _axis_titles_from_variance(embedding_df: pd.DataFrame, dims: int = 2):
    evr = embedding_df.attrs.get("explained_variance_ratio", None)
    if evr is None or len(evr) < dims:
        if dims == 2:
            return "PC1", "PC2"
        return "PC1", "PC2", "PC3"

    if dims == 2:
        return (
            f"PC1 ({evr[0]*100:.1f}% var)",
            f"PC2 ({evr[1]*100:.1f}% var)",
        )
    return (
        f"PC1 ({evr[0]*100:.1f}% var)",
        f"PC2 ({evr[1]*100:.1f}% var)",
        f"PC3 ({evr[2]*100:.1f}% var)",
    )


def plot_embedding_2d(embedding_df: pd.DataFrame, selected: str, neighbors: list[str]):
    df = _add_roles(embedding_df, selected, neighbors)

    role_order = {"other": 0, "neighbor": 1, "selected": 2}
    df["role_order"] = df["role"].map(role_order)
    df = df.sort_values("role_order")

    df = _apply_small_jitter(df, ["embedding_x", "embedding_y"])

    x_title, y_title = _axis_titles_from_variance(embedding_df, dims=2)

    fig = px.scatter(
        df,
        x="embedding_x",
        y="embedding_y",
        hover_name="product",
        color="role",
        title="2D embedding (PCA)",
        color_discrete_map={
            "other": "#b0b0b0",
            "neighbor": "#ff6b6b",
            "selected": "#1f77b4",
        }
    )

    for tr in fig.data:
        if tr.name == "other":
            tr.marker.size = 7
            tr.marker.opacity = 0.45
        elif tr.name == "neighbor":
            tr.marker.size = 10
            tr.marker.opacity = 0.9
        elif tr.name == "selected":
            tr.marker.size = 14
            tr.marker.opacity = 1.0
            tr.marker.line = dict(width=2)

    fig.update_layout(
        height=600,
        xaxis_title=x_title,
        yaxis_title=y_title,
        legend_title_text="role",
    )
    return fig


def plot_embedding_3d(embedding_df: pd.DataFrame, selected: str, neighbors: list[str]):
    if "embedding_z" not in embedding_df.columns:
        raise ValueError("embedding_df must contain 'embedding_z' for 3D plotting.")

    df = _add_roles(embedding_df, selected, neighbors)

    role_order = {"other": 0, "neighbor": 1, "selected": 2}
    df["role_order"] = df["role"].map(role_order)
    df = df.sort_values("role_order")

    df = _apply_small_jitter(df, ["embedding_x", "embedding_y", "embedding_z"])

    x_title, y_title, z_title = _axis_titles_from_variance(embedding_df, dims=3)

    fig = px.scatter_3d(
        df,
        x="embedding_x",
        y="embedding_y",
        z="embedding_z",
        hover_name="product",
        color="role",
        title="3D embedding (PCA)",
        color_discrete_map={
            "other": "#b0b0b0",
            "neighbor": "#ff6b6b",
            "selected": "#1f77b4",
        }
    )

    for tr in fig.data:
        if tr.name == "other":
            tr.marker.size = 4
            tr.marker.opacity = 0.35
        elif tr.name == "neighbor":
            tr.marker.size = 6
            tr.marker.opacity = 0.9
        elif tr.name == "selected":
            tr.marker.size = 8
            tr.marker.opacity = 1.0

    fig.update_layout(
        height=700,
        legend_title_text="role",
        scene=dict(
            xaxis_title=x_title,
            yaxis_title=y_title,
            zaxis_title=z_title,
            aspectmode="cube",
        ),
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


# 2D raw feature scatter
def compute_raw_feature_view(
    preprocessed_numeric: pd.DataFrame,
    product_keys: list[str],
    x_feature: str,
    y_feature: str,
) -> pd.DataFrame:
    product_keys = [_clean_str(p) for p in product_keys]
    x_feature = _clean_str(x_feature)
    y_feature = _clean_str(y_feature)

    if len(product_keys) != len(preprocessed_numeric):
        raise ValueError(
            "Row count mismatch: preprocessed_numeric and product_keys must have the same length. "
            f"Got {len(preprocessed_numeric)} rows and {len(product_keys)} product keys."
        )

    missing = [c for c in [x_feature, y_feature] if c not in preprocessed_numeric.columns]
    if missing:
        raise ValueError(f"Selected raw feature(s) not found: {missing}")

    df = preprocessed_numeric[[x_feature, y_feature]].copy()

    if df.isna().any().any():
        df = df.fillna(df.mean(numeric_only=True))

    out = pd.DataFrame({
        "product": product_keys,
        "raw_x": df[x_feature].to_numpy(),
        "raw_y": df[y_feature].to_numpy(),
    })
    out.attrs["x_feature"] = x_feature
    out.attrs["y_feature"] = y_feature
    return out


def plot_raw_feature_scatter_2d(raw_df: pd.DataFrame, selected: str, neighbors: list[str]):
    df = _add_roles(raw_df, selected, neighbors)

    role_order = {"other": 0, "neighbor": 1, "selected": 2}
    df["role_order"] = df["role"].map(role_order)
    df = df.sort_values("role_order")

    df = _apply_small_jitter(df, ["raw_x", "raw_y"])

    x_title = raw_df.attrs.get("x_feature", "x")
    y_title = raw_df.attrs.get("y_feature", "y")

    fig = px.scatter(
        df,
        x="raw_x",
        y="raw_y",
        hover_name="product",
        color="role",
        title=f"2D raw feature scatter: {x_title} vs {y_title}",
        color_discrete_map={
            "other": "#b0b0b0",
            "neighbor": "#ff6b6b",
            "selected": "#1f77b4",
        }
    )

    for tr in fig.data:
        if tr.name == "other":
            tr.marker.size = 7
            tr.marker.opacity = 0.45
        elif tr.name == "neighbor":
            tr.marker.size = 10
            tr.marker.opacity = 0.9
        elif tr.name == "selected":
            tr.marker.size = 14
            tr.marker.opacity = 1.0
            tr.marker.line = dict(width=2)

    fig.update_layout(
        height=600,
        xaxis_title=x_title,
        yaxis_title=y_title,
        legend_title_text="role",
    )
    return fig


# =========================
# dashboard_inputs export
# =========================
def nearest_neighbor_distance(dm: pd.DataFrame) -> pd.Series:
    nn = []
    for p in dm.index:
        s = dm.loc[p].drop(index=p, errors="ignore")
        nn.append(float(s.min()))
    return pd.Series(nn, index=dm.index, name="nearest_neighbor_distance")


def export_dashboard_inputs(
    embedding_df: pd.DataFrame,
    dm: pd.DataFrame,
    out_path: str | Path,
):
    out = embedding_df.copy()
    out["product"] = out["product"].astype(str).str.strip()

    nn_dist = nearest_neighbor_distance(dm)
    nn_map = {str(k).strip(): float(v) for k, v in nn_dist.items()}
    out["nearest_neighbor_distance"] = out["product"].map(nn_map)

    ordered_cols = ["product", "embedding_x", "embedding_y"]
    if "embedding_z" in out.columns:
        ordered_cols.append("embedding_z")
    ordered_cols.append("nearest_neighbor_distance")
    out = out[ordered_cols]

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)


# =========================
# One-call bundle
# =========================
def generate_task2_artifacts(
    outputs_dir: str | Path,
    dataset: str,
    selected_product: str | None = None,
    selected_features: list[str] | None = None,
    k: int = 10,
    nbins: int = 40,
    html_include_plotlyjs: str = "cdn",
):

    paths = dataset_paths(outputs_dir, dataset)

    for key in ["pre", "dm", "nn"]:
        if not paths[key].exists():
            raise FileNotFoundError(f"Missing required file for {dataset}: {paths[key]}")

    nn_df = load_neighbors_table(paths["nn"])
    dm = load_distance_matrix(paths["dm"])
    pre = load_preprocessed_numeric(paths["pre"], selected_features=selected_features)

    if selected_product is None:
        selected_product = sorted(nn_df["product"].unique())[0]
    selected_product = _clean_str(selected_product)

    neigh_df = neighbors_for_product(nn_df, selected_product, k=k)
    fig_neigh = plot_neighbor_bar(neigh_df, selected_product)
    fig_hist = plot_distance_histogram(dm, nbins=nbins)

    # 2D PCA
    emb_df_2d = compute_pca_embedding(pre, list(dm.index), n_components=2)
    fig_pca_2d = plot_embedding_2d(
        emb_df_2d,
        selected_product,
        neighbors=list(neigh_df["neighbor"])
    )

    # 3D PCA
    emb_df_3d = None
    fig_pca_3d = None
    if pre.shape[1] >= 3:
        emb_df_3d = compute_pca_embedding(pre, list(dm.index), n_components=3)
        fig_pca_3d = plot_embedding_3d(
            emb_df_3d,
            selected_product,
            neighbors=list(neigh_df["neighbor"])
        )

    # export dashboard inputs
    export_df = emb_df_3d if emb_df_3d is not None else emb_df_2d
    export_dashboard_inputs(export_df, dm, paths["dashboard_inputs"])

    # save htmls
    paths["base"].mkdir(parents=True, exist_ok=True)
    fig_neigh.write_html(paths["fig_neighbor"], include_plotlyjs=html_include_plotlyjs)
    fig_hist.write_html(paths["fig_hist"], include_plotlyjs=html_include_plotlyjs)
    fig_pca_2d.write_html(paths["fig_pca_2d"], include_plotlyjs=html_include_plotlyjs)

    if fig_pca_3d is not None:
        fig_pca_3d.write_html(paths["fig_pca_3d"], include_plotlyjs=html_include_plotlyjs)

    return {
        "paths": paths,
        "selected_product": selected_product,
        "selected_features": selected_features,
        "available_numeric_features": get_available_numeric_features(paths["pre"]),
        "neighbors_df": neigh_df,
        "embedding_df_2d": emb_df_2d,
        "embedding_df_3d": emb_df_3d,
        "fig_neighbor": fig_neigh,
        "fig_hist": fig_hist,
        "fig_pca_2d": fig_pca_2d,
        "fig_pca_3d": fig_pca_3d,
    }