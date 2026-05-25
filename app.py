import streamlit as st
import pandas as pd
import os

from dashboard.viz import (
    dataset_paths,
    load_distance_matrix,
    load_neighbors_table,
    load_preprocessed_numeric,
    compute_pca_embedding,
    plot_embedding_2d,
    plot_embedding_3d,
    plot_distance_histogram,
    plot_neighbor_bar,
    get_available_numeric_features,
    compute_raw_feature_view,
    plot_raw_feature_scatter_2d,
)
from dashboard.comparison import (
    build_side_by_side_neighbors,
    load_importance,
    plot_importance_pie,
    resolve_view,
)

st.set_page_config(page_title="Strategic Product Optimizer", layout="wide")
st.title("Product Portfolio Analysis")

# Sidebar for category selection. "Conjoint Demo" carries real conjoint
# attributes (weighted by the published N=381 study), so it is the dataset whose
# Customer-weighted view actually has data — see ./run.sh conjoint.
category = st.sidebar.selectbox(
    "Select Product Category",
    ["Smartphones", "Tractors", "User Upload", "Conjoint Demo"]
)

folder_name = category.lower().replace(" ", "_")
base_path = os.path.join("outputs", folder_name)

paths = dataset_paths("outputs", folder_name)

# --- VIEW TOGGLE: technical vs customer-weighted (Module 5) ---
view_label = st.sidebar.radio(
    "View",
    ["Technical", "Customer-weighted"],
    help=(
        "Technical: uniform-weight distance over all preprocessed features. "
        "Customer-weighted: distance re-scaled by conjoint relative importance "
        "(Module 4). Falls back to technical when weighted artifacts are absent."
    ),
)
requested_view = "weighted" if view_label == "Customer-weighted" else "technical"

# Resolve which distance/neighbour artifacts to use; degrade gracefully.
resolved = resolve_view(paths, requested_view)
nn_path = str(resolved["nn"])
dm_path = str(resolved["dm"])
pre_path = os.path.join(base_path, "preprocessed_output.csv")
summary_path = os.path.join(base_path, "distance_summary.txt")
active_view = resolved["view"]

if resolved["fell_back"]:
    st.info(str(resolved["reason"]))

if active_view == "weighted":
    st.caption("Distance view: **Customer-weighted** (conjoint relative importance).")
else:
    st.caption("Distance view: **Technical** (uniform feature weighting).")

# --- DISPLAY SUMMARY STATS ---
if os.path.exists(summary_path):
    with open(summary_path, 'r') as f:
        summary_text = f.read()
    st.sidebar.info(f"**Category Summary:**\n\n{summary_text}")

# --- PRE-LOAD NUMERIC DATA (needed for feature comparison + PCA) ---
# NOTE: PCA / raw scatter always read the *technical* preprocessed feature
# matrix (preprocessed_output.csv). The customer-weighted view only re-scales
# the distance matrix + neighbours; it does not change the underlying feature
# space, so the spatial layout (PCA, raw scatter) stays comparable across views.
pre = None
dm = None
if os.path.exists(pre_path):
    pre = load_preprocessed_numeric(pre_path)
if os.path.exists(dm_path):
    dm = load_distance_matrix(dm_path)

if pre is not None and dm is not None and len(pre) == len(dm):
    pre.index = dm.index

# --- MAIN ANALYSIS ---
if os.path.exists(nn_path):
    nn_df = pd.read_csv(nn_path)
    st.session_state['df'] = nn_df
    if dm is not None:
        st.session_state['dist_matrix'] = dm.values

    # Selection UI
    product_list = sorted(nn_df.iloc[:, 0].unique())
    selected_product = st.selectbox("Select a Product to find neighbors", product_list)

    # Filter Results
    results = nn_df[nn_df.iloc[:, 0] == selected_product].sort_values('distance')

    # Layout with Columns
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader(f"Top Nearest Neighbors for {selected_product}")
        display_results = results.iloc[:, [2, -1]].head(5)
        display_results.columns = ['Neighbor Name', 'Distance Score']
        st.table(display_results)

    with col2:
        st.subheader("Market Impact Analysis")
        top_neighbor_dist = results['distance'].iloc[0]
        closest_neighbor_name = results.iloc[0, 2]

        # Compare specs feature-by-feature to explain WHY
        diffs = None
        if pre is not None and selected_product in pre.index and closest_neighbor_name in pre.index:
            p1_specs = pre.loc[selected_product]
            p2_specs = pre.loc[closest_neighbor_name]
            diffs = (p1_specs - p2_specs).abs().sort_values()

        # Display Alerts with Strategic Business Insights
        if top_neighbor_dist < 0.05:
            st.error(f"🔴 Cannibalization Risk (Dist: {top_neighbor_dist:.4f})")
            st.markdown(
                f"**{selected_product}** and **{closest_neighbor_name}** are near-identical in the market. "
                "Keeping both creates internal competition and dilutes market share."
            )
            if diffs is not None:
                overlap_features = ", ".join(diffs.index[:5])
                st.markdown(f"**Overlapping specs:** {overlap_features}")
                st.markdown("**💡 Recommendation:** Consider rationalizing/removing one product from the portfolio. "
                           "Consolidating into a single SKU can reduce costs and strengthen positioning.")

        elif top_neighbor_dist < 0.50:
            st.warning(f"🟡 Significant Overlap (Dist: {top_neighbor_dist:.4f})")
            st.markdown(
                f"**{selected_product}** competes closely with **{closest_neighbor_name}**. "
                "Consumers may struggle to distinguish between the two."
            )
            if diffs is not None:
                shared_list = diffs.index[:5].tolist()
                shared_features = ", ".join(shared_list)
                
                diff_candidates = [f for f in diffs.tail(5).index[::-1] if f not in shared_list]
                diff_features = ", ".join(diff_candidates[:3])
                st.markdown(f"**Shared ground:** {shared_features}")
                st.markdown(f"**Key differentiators to leverage:** {diff_features}")
                st.markdown("**💡 Recommendation:** Sharpen the value proposition — emphasize the differentiating "
                           "features in marketing to carve out distinct customer segments.")

        else:
            st.success(f"🟢 Unique Positioning (Dist: {top_neighbor_dist:.4f})")
            st.markdown(
                f"**{selected_product}** is well-differentiated from its nearest competitor "
                f"**{closest_neighbor_name}**. It occupies a distinct market position."
            )
            if diffs is not None:
                strengths = ", ".join(diffs.tail(5).index[::-1])
                st.markdown(f"**Competitive advantages:** {strengths}")
                st.markdown("**💡 Recommendation:** Invest in distribution and marketing to maximize reach. "
                           "This product fills a unique gap in the portfolio — protect and develop it.")

        st.caption("Alert Logic: 🔴 Cannibalization < 0.05 | 🟡 Overlap < 0.50 | 🟢 Unique > 0.50")

    # --- Module 5: Customer importance + technical vs weighted comparison ---
    importance_path = paths["importance"]
    comp_col1, comp_col2 = st.columns([1, 1])

    with comp_col1:
        st.subheader("Customer Importance")
        if importance_path.exists():
            importance_df = load_importance(importance_path)
            st.plotly_chart(plot_importance_pie(importance_df), use_container_width=True)
            st.caption(
                "Relative importance per attribute from the conjoint survey "
                "(WTP / Part-C is display-only and excluded by design)."
            )
        else:
            st.info(
                "No `importance.csv` for this category — run the conjoint "
                "importance step to populate the customer-weighted view."
            )

    with comp_col2:
        st.subheader("Neighbors: Technical vs Customer-weighted")
        nn_tech_path = paths["nn"]
        nn_weighted_path = paths["nn_weighted"]
        if nn_tech_path.exists() and nn_weighted_path.exists():
            nn_technical = load_neighbors_table(nn_tech_path)
            nn_weighted = load_neighbors_table(nn_weighted_path)
            side_by_side = build_side_by_side_neighbors(
                nn_technical, nn_weighted, selected_product, k=5
            )
            side_by_side = side_by_side.rename(
                columns={
                    "rank": "Rank",
                    "technical_neighbor": "Technical Neighbor",
                    "technical_distance": "Technical Dist",
                    "weighted_neighbor": "Weighted Neighbor",
                    "weighted_distance": "Weighted Dist",
                }
            )
            st.dataframe(side_by_side, hide_index=True, use_container_width=True)
            st.caption(
                "Rank-aligned: how the nearest competitors shift when distance "
                "is weighted by what customers care about."
            )
        else:
            st.info(
                "Customer-weighted neighbours unavailable — showing the "
                "technical view only. Run Module 4's weighted distance to "
                "enable this comparison."
            )

    # --- Task 2 Visualizations ---
    if dm is not None and pre is not None:
        st.subheader("Visual Analytics")

        # 1) Neighbor bar
        topk = results.sort_values("distance").head(10)
        nb_df = topk.iloc[:, [2, -1]].copy()
        nb_df.columns = ["neighbor", "distance"]
        st.plotly_chart(plot_neighbor_bar(nb_df, selected_product), use_container_width=True)

        # 2) Distance histogram
        st.plotly_chart(plot_distance_histogram(dm), use_container_width=True)

        # 3) Feature selector + 2D / 3D PCA
        st.markdown("### PCA Feature Selection")

        available_features = get_available_numeric_features(pre_path)
        selected_features = st.multiselect(
            "Select numeric features to include in PCA",
            options=available_features,
            default=available_features,
            key=f"pca_features_{folder_name}"
        )

        if len(selected_features) < 2:
            st.warning("Please select at least 2 numeric features to generate a 2D PCA view.")
        else:
            pre_pca = load_preprocessed_numeric(pre_path, selected_features=selected_features)

            if len(pre_pca) == len(dm):
                pre_pca.index = dm.index

            # 2D PCA
            emb_df_2d = compute_pca_embedding(pre_pca, list(dm.index), n_components=2)
            st.plotly_chart(
                plot_embedding_2d(
                    emb_df_2d,
                    selected=selected_product,
                    neighbors=nb_df["neighbor"].tolist()
                ),
                use_container_width=True
            )

            # 3D PCA
            st.markdown("### 3D PCA View")
            if len(selected_features) >= 3:
                emb_df_3d = compute_pca_embedding(pre_pca, list(dm.index), n_components=3)
                st.plotly_chart(
                    plot_embedding_3d(
                        emb_df_3d,
                        selected=selected_product,
                        neighbors=nb_df["neighbor"].tolist()
                    ),
                    use_container_width=True
                )
            else:
                st.info("Select at least 3 numeric features to display the 3D PCA view.")
        # 4) Raw feature scatter with user-defined axes
        st.markdown("### 2D Raw Feature Comparison")

        raw_x = st.selectbox(
            "Select x-axis feature",
            options=available_features,
            index=0,
            key=f"raw_x_{folder_name}"
        )

        default_y_index = 1 if len(available_features) > 1 else 0
        raw_y = st.selectbox(
            "Select y-axis feature",
            options=available_features,
            index=default_y_index,
            key=f"raw_y_{folder_name}"
        )

        if raw_x == raw_y:
            st.info("Please choose two different features for the raw 2D scatter.")
        else:
            raw_df = compute_raw_feature_view(
                pre,
                list(dm.index),
                x_feature=raw_x,
                y_feature=raw_y,
            )
            st.plotly_chart(
                plot_raw_feature_scatter_2d(
                    raw_df,
                    selected=selected_product,
                    neighbors=nb_df["neighbor"].tolist()
                ),
                use_container_width=True
            )
    else:
        st.warning("Missing distance_matrix.csv or preprocessed_output.csv for visualizations.")

else:
    st.error(f"No analysis data found for {category}. Please ensure the distance matrix script has been run.")

# --- Task 3: Product Removal Simulation ---
st.markdown("---")
st.subheader("Simulation: Product Removal")

from dashboard.simulation import simulate_removal

if os.path.exists(nn_path):
    products_to_remove = st.multiselect("Select Products to Remove", product_list)
    threshold = st.number_input("Optional Gap Threshold", min_value=0.0, value=0.0)

    if st.button("Simulate Removal"):
        if dm is not None:
            result = simulate_removal(dm, st.session_state['dist_matrix'], products_to_remove, threshold)

            if 'error' in result:
                st.error(result['error'])
            else:
                st.write(f"Mean Substitute Distance: {result['mean_dist']:.2f}")
                st.write(f"Max Substitute Distance: {result['max_dist']:.2f}")

                st.subheader("Substitutes")
                for removed, info in result['substitutes'].items():
                    st.write(f"- Removed {removed} → Substitute {info['substitute']} (dist {info['distance']:.2f})")

                if threshold:
                    st.write("Gaps:", ", ".join(result.get('gaps', [])))
        else:
            st.error("Distance matrix not available. Cannot run simulation.")