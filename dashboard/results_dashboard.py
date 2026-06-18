"""Standalone dashboard page: ACBC **survey results** (run via ``results_app.py``).

This is the business-facing read-out of a fielded conjoint survey, distinct from
``app.py`` (portfolio/distance) and ``quality_diagnostics.py`` (data quality /
model diagnostics). It composes :func:`dashboard.results_analysis.analyze_survey_results`
and renders seven sections:

1. Overview / sample (N, tasks, HB convergence)
2. Attribute importance
3. Part-worth utilities
4. Willingness-to-pay (stated Part C + derived $/util)
5. Market simulator (configure products → share of preference + removal)
6. Purchase likelihood (B5 calibration)
7. Respondent segments (Part A background)

The pure logic lives in :mod:`dashboard.results_analysis`; the ``_render_*``
helpers below take an explicit ``st`` so they stay unit-testable. Streamlit is
imported lazily (inside :func:`render_results_dashboard` and the cache wrappers)
so this module imports cleanly without a Streamlit runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

from conjoint.acbc import simulation as sim
from conjoint.acbc.responses import (
    RESPONSE_VALUE_COL,
    STAGE_COL,
    STAGE_TOURNAMENT,
    read_acbc_responses,
)
from dashboard.results_analysis import SurveyResults, analyze_survey_results

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Survey context (spec, banks, labels) — product-agnostic, env-resolved
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SurveyContext:
    spec: object
    questions: tuple
    features: tuple
    bands: tuple
    labels: dict  # {attribute: {level_code: label}}
    feature_attribute: dict  # {wtp_feature_id: attribute}
    attribute_levels: "dict"


def _spec_path() -> Path:
    return Path(os.environ.get("SURVEY_SPEC") or ROOT / "questionnaire_spec.json")


def load_context() -> SurveyContext:
    """Resolve spec + Part A/C banks + label maps the same way the app does."""
    from conjoint import questionnaire as q
    from conjoint.acbc import respondent_sim as rs
    from conjoint.acbc.design import attribute_levels_from_spec
    from survey_views import section_source as ss

    spec = q.read_spec(_spec_path())
    workbook = os.environ.get("SURVEY_WORKBOOK")
    questions = ss.load_background_questions(workbook)
    features = ss.load_wtp_features(workbook)
    bands = ss.load_amount_bands(workbook)
    attribute_levels = attribute_levels_from_spec(spec)
    labels = {
        attr.feature_name: {level.code: level.label for level in attr.levels}
        for attr in spec.attributes
    }
    return SurveyContext(
        spec=spec,
        questions=questions,
        features=features,
        bands=bands,
        labels=labels,
        feature_attribute=rs.default_wtp_feature_attribute(features, attribute_levels),
        attribute_levels=attribute_levels,
    )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def attr_name(name: str) -> str:
    """Human-facing attribute heading (``ram`` → ``RAM``, ``os`` → ``OS``)."""
    cleaned = str(name).replace("_", " ").strip()
    if not cleaned:
        return str(name)
    if " " not in cleaned and len(cleaned) <= 3:
        return cleaned.upper()
    return cleaned.title()


def level_label(ctx: SurveyContext, attribute: str, code: str) -> str:
    return ctx.labels.get(attribute, {}).get(code, code)


def feature_label(ctx: SurveyContext, feature_id: str) -> str:
    for feature in ctx.features:
        if feature.identifier == feature_id:
            return feature.label
    return feature_id


def band_label(ctx: SurveyContext, code: str) -> str:
    return dict(ctx.bands).get(code, code)


# ---------------------------------------------------------------------------
# Streamlit caching wrappers (thin; the core stays pure/testable)
# ---------------------------------------------------------------------------
def _cached_synthetic(n_respondents: int, seed: int) -> pd.DataFrame:
    import streamlit as st

    @st.cache_data(show_spinner="Generating synthetic responses…")
    def _gen(n: int, s: int) -> pd.DataFrame:
        from conjoint.acbc import respondent_sim as rs

        ctx = load_context()
        frame, _, _ = rs.generate_synthetic_responses(
            ctx.spec,
            questions=ctx.questions,
            wtp_features=ctx.features,
            amount_bands=ctx.bands,
            wtp_feature_attribute=ctx.feature_attribute,
            n_respondents=n,
            seed=s,
        )
        return frame

    return _gen(n_respondents, seed)


def _cached_results(df: pd.DataFrame, hb_iter: int, seed: int) -> SurveyResults:
    import streamlit as st

    @st.cache_data(show_spinner="Fitting MNL + Hierarchical Bayes model…")
    def _run(frame: pd.DataFrame, iters: int, s: int) -> SurveyResults:
        ctx = load_context()
        return analyze_survey_results(
            frame,
            amount_bands=ctx.bands,
            price_labels=ctx.labels.get("price"),
            hb_iter=iters,
            seed=s,
        )

    return _run(df, hb_iter, seed)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def render_results_dashboard() -> None:
    """Render the standalone ACBC results page (called from ``results_app.py``)."""
    import streamlit as st

    st.title("Conjoint Results")
    st.caption(
        "Hierarchical Bayes part-worth utilities fitted from the B4 choices, covering "
        "attribute importance, part-worth utilities, willingness to pay, market "
        "simulation, purchase likelihood and respondent segments."
    )

    ctx = load_context()
    df = _load_responses(st, ctx)
    if df is None:
        return

    hb_iter = int(
        st.sidebar.select_slider(
            "HB iterations",
            options=[200, 400, 1000, 2000, 4000],
            value=400,
            help="400 is a preview setting (Rhat may exceed 1.1); use >= 4000 for publication-quality results.",
        )
    )
    seed = int(st.sidebar.number_input("Random seed", value=0, step=1))

    try:
        results = _cached_results(df, hb_iter, seed)
    except Exception as exc:  # never crash the dashboard over a fit error
        st.error(f"Analysis failed: {exc}")
        return

    _render_overview(st, results)
    st.markdown("---")
    _render_importance(st, results, ctx)
    st.markdown("---")
    _render_partworths(st, results, ctx)
    st.markdown("---")
    _render_wtp(st, results, ctx)
    st.markdown("---")
    _render_simulator(st, results, ctx)
    st.markdown("---")
    _render_calibration(st, results)
    st.markdown("---")
    _render_segments(st, results, ctx)


def _load_responses(st, ctx: SurveyContext) -> pd.DataFrame | None:
    """Data-source picker → validated long-format frame (or ``None``)."""
    source = st.sidebar.radio(
        "Data source",
        ["Synthetic responses", "Upload CSV", "Local path"],
        help="Requires a long-format acbc_responses.csv; by default a synthetic dataset is generated on the fly.",
    )
    df: pd.DataFrame | None = None
    if source == "Synthetic responses":
        n = int(st.sidebar.slider("Respondents (N)", min_value=20, max_value=500, value=200, step=10))
        seed = int(st.sidebar.number_input("Generation seed", value=2026, step=1))
        df = _cached_synthetic(n, seed)
        st.sidebar.download_button(
            "Download this synthetic CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="synthetic_responses.csv",
            mime="text/csv",
        )
    elif source == "Upload CSV":
        uploaded = st.sidebar.file_uploader("acbc_responses.csv", type="csv")
        if uploaded is None:
            st.info("Please upload a long-format acbc_responses.csv in the sidebar.")
            return None
        df = pd.read_csv(uploaded)
    else:
        stem = _spec_path().stem.replace("questionnaire_spec", "").strip("_") or "default"
        default_path = f"outputs/synthetic_responses_{stem}.csv"
        path = st.sidebar.text_input("CSV path", value=default_path)
        if not path:
            return None
        try:
            df = read_acbc_responses(path)
        except Exception as exc:
            st.error(f"Read failed: {exc}")
            return None

    if STAGE_COL not in df.columns or not (df[STAGE_COL] == STAGE_TOURNAMENT).any():
        st.error("This file has no tournament rows, so ACBC estimation is not possible.")
        return None
    return df


# ---------------------------------------------------------------------------
# Section 1 — Overview
# ---------------------------------------------------------------------------
def _render_overview(st, results: SurveyResults) -> None:
    st.subheader("Overview & convergence")
    col1, col2, col3 = st.columns(3)
    col1.metric("Respondents", f"{results.n_respondents}")
    col2.metric("Tournament tasks", f"{results.n_tournament_tasks}")
    converged = results.rhat_max < 1.1
    col3.metric(
        "HB convergence (Rhat max)",
        f"{results.rhat_max:.2f}",
        help="Gelman-Rubin < 1.1 indicates convergence. It runs high with few preview iterations; just raise the iteration count.",
    )
    col3.caption("Converged" if converged else "Preview run (consider raising HB iterations)")


# ---------------------------------------------------------------------------
# Section 2 — Attribute importance
# ---------------------------------------------------------------------------
def _render_importance(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("Attribute importance")
    imp = results.importance.copy()
    imp["Attribute"] = imp["attribute"].map(attr_name)
    imp = imp.sort_values("relative_importance")
    fig = px.bar(
        imp,
        x="relative_importance",
        y="Attribute",
        orientation="h",
        text=imp["relative_importance"].map(lambda v: f"{v:.1%}"),
        title="Relative importance (Range_A / ΣRange)",
    )
    fig.update_layout(xaxis_tickformat=".0%", xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    top = imp.sort_values("relative_importance", ascending=False).iloc[0]
    st.caption(
        f"The most important attribute is **{top['Attribute']}** "
        f"({top['relative_importance']:.1%}); a longer bar means the attribute has a "
        "greater influence on choice."
    )


# ---------------------------------------------------------------------------
# Section 3 — Part-worth utilities
# ---------------------------------------------------------------------------
def _partworths_long(results: SurveyResults, ctx: SurveyContext) -> pd.DataFrame:
    rows = [
        {
            "attribute": attribute,
            "Attribute": attr_name(attribute),
            "level": level,
            "Level": level_label(ctx, attribute, level),
            "Utility": float(value),
        }
        for attribute, per_level in results.rescaled_utilities.items()
        for level, value in per_level.items()
    ]
    return pd.DataFrame(rows)


def _render_partworths(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("Part-worth utilities")
    st.caption("Zero-centered \"diffs\" scale (mean range per attribute = 100); higher utility means more preferred.")
    tidy = _partworths_long(results, ctx)
    attributes = list(results.rescaled_utilities.keys())
    chosen = st.selectbox(
        "Select attribute",
        options=attributes,
        index=0,
        format_func=attr_name,
        key="pw_attribute",
    )
    block = tidy[tidy["attribute"] == chosen]
    fig = px.bar(
        block,
        x="Utility",
        y="Level",
        orientation="h",
        text=block["Utility"].map(lambda v: f"{v:+.0f}"),
        title=f"{attr_name(chosen)} — utility by level",
    )
    fig.update_layout(xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Show part-worth utilities for all attributes"):
        st.dataframe(
            tidy[["Attribute", "Level", "Utility"]].round(1),
            hide_index=True,
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Section 4 — Willingness-to-pay
# ---------------------------------------------------------------------------
def _render_wtp(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("Willingness-to-pay")
    left, right = st.columns(2)

    with left:
        st.markdown("**Stated WTP (Part C)** — how much extra respondents will pay for an upgrade")
        if results.wtp is None:
            st.info("This dataset has no Part C (WTP) records.")
        else:
            rows = []
            for feature_id, fw in results.wtp.features.items():
                rows.append(
                    {
                        "Feature": feature_label(ctx, feature_id),
                        "Modal band": band_label(ctx, fw.modal_band),
                        "Share willing to pay": f"{fw.share_paid:.0%}",
                        "Mean premium ($)": (f"${fw.mean_usd:,.0f}" if fw.mean_usd is not None else "—"),
                    }
                )
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            feature_ids = list(results.wtp.features.keys())
            picked = st.selectbox(
                "View band distribution for a feature",
                options=feature_ids,
                index=0,
                format_func=lambda fid: feature_label(ctx, fid),
                key="wtp_feature",
            )
            fw = results.wtp.features[picked]
            dist = pd.DataFrame(
                {
                    "Band": [band_label(ctx, code) for code in fw.band_counts],
                    "Count": list(fw.band_counts.values()),
                }
            )
            fig = px.bar(dist, x="Band", y="Count", title=feature_label(ctx, picked))
            fig.update_layout(xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("**Derived WTP** — dollar value converted from the price part-worth utilities")
        derived = results.derived_wtp
        if not derived.available:
            st.info(f"Monetary WTP cannot be derived: {derived.note}.")
        else:
            st.caption(f"1 utility unit ≈ **${derived.usd_per_util:,.0f}** (derived from the price-band slope).")
            table = derived.per_attribute.copy()
            table["Attribute"] = table["attribute"].map(attr_name)
            table["Level"] = [
                level_label(ctx, a, lv) for a, lv in zip(table["attribute"], table["level"])
            ]
            table["Value vs. worst level ($)"] = table["usd_vs_worst"].map(lambda v: f"${v:,.0f}")
            st.dataframe(
                table[["Attribute", "Level", "Value vs. worst level ($)"]],
                hide_index=True,
                use_container_width=True,
            )


# ---------------------------------------------------------------------------
# Section 5 — Market simulator
# ---------------------------------------------------------------------------
def _default_product_spec(ctx: SurveyContext, index: int) -> dict:
    """A differentiated default config: product ``index`` takes its ``index``-th level."""
    spec = {}
    for attribute, levels in ctx.attribute_levels.items():
        spec[attribute] = levels[min(index, len(levels) - 1)]
    return spec


def _render_simulator(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("Market simulator")
    st.caption("Configure competing products and compute share of preference from each respondent's HB utilities.")

    n_products = int(st.number_input("Number of products", min_value=2, max_value=4, value=2, step=1))
    attributes = list(ctx.attribute_levels.keys())
    products: dict[str, dict] = {}
    columns = st.columns(n_products)
    for index in range(n_products):
        default = _default_product_spec(ctx, index)
        name = f"Product {chr(65 + index)}"
        with columns[index]:
            st.markdown(f"**{name}**")
            spec: dict[str, str] = {}
            for attribute in attributes:
                levels = list(ctx.attribute_levels[attribute])
                spec[attribute] = st.selectbox(
                    attr_name(attribute),
                    options=levels,
                    index=levels.index(default[attribute]),
                    format_func=lambda code, a=attribute: level_label(ctx, a, code),
                    key=f"sim_{index}_{attribute}",
                )
        products[name] = spec

    utilities = sim.utilities_from_frame(results.hb_utilities, results.level_map)
    shares = sim.aggregate_shares([sim.share_of_preference(u, products) for u in utilities])
    share_df = pd.DataFrame(
        {"Product": list(shares.keys()), "Share": list(shares.values())}
    )
    fig = px.bar(
        share_df,
        x="Product",
        y="Share",
        text=share_df["Share"].map(lambda v: f"{v:.1%}"),
        title="Share of preference",
    )
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

    to_remove = st.multiselect(
        "Remove product(s) to see share transfer",
        options=list(products.keys()),
    )
    if to_remove and len(to_remove) < len(products):
        impact = sim.removal_impact(utilities, products, to_remove)
        transfer = impact.transfer.rename(
            columns={
                "product": "Product",
                "removed": "Removed",
                "share_before": "Share before",
                "share_after": "Share after",
                "delta": "Change",
            }
        )
        for column in ("Share before", "Share after", "Change"):
            transfer[column] = transfer[column].map(lambda v: f"{v:.1%}")
        st.dataframe(transfer, hide_index=True, use_container_width=True)
        st.caption("A positive \"Change\" means the product absorbed share from the removed product(s).")


# ---------------------------------------------------------------------------
# Section 6 — Purchase likelihood (B5 calibration)
# ---------------------------------------------------------------------------
def _render_calibration(st, results: SurveyResults) -> None:
    import plotly.express as px

    st.subheader("Purchase likelihood (B5)")
    cal = results.calibration
    if cal is None:
        st.info("This dataset has no B5 calibration records.")
        return
    col1, col2 = st.columns([1, 2])
    col1.metric("Mean purchase likelihood", f"{cal.mean_probability_pct:.0f}%", help="B5 rating 0-5, converted to a percentage.")
    dist = pd.DataFrame(
        {"Purchase intent (0-5)": list(cal.distribution.keys()), "Count": list(cal.distribution.values())}
    )
    fig = px.bar(dist, x="Purchase intent (0-5)", y="Count", title="Purchase intent distribution (0 = never buy, 5 = definitely buy)")
    fig.update_layout(xaxis_title="", yaxis_title="")
    col2.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 7 — Respondent segments (Part A)
# ---------------------------------------------------------------------------
def _render_segments(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("Respondent segments (Part A)")
    background = results.background
    if background is None or not background.questions:
        st.info("This dataset has no Part A (background) records.")
        return

    def _prompt(question_id: str) -> str:
        for question in ctx.questions:
            if question.identifier == question_id:
                return question.prompt
        return question_id

    question_ids = list(background.questions.keys())
    picked = st.selectbox(
        "Select background question",
        options=question_ids,
        index=0,
        format_func=_prompt,
        key="segment_question",
    )
    counts = background.questions[picked]
    dist = pd.DataFrame(
        {"Answer": list(counts.keys()), "Count": list(counts.values())}
    ).sort_values("Count")
    fig = px.bar(
        dist,
        x="Count",
        y="Answer",
        orientation="h",
        title=_prompt(picked),
    )
    fig.update_layout(xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":  # pragma: no cover — manual ``streamlit run``
    render_results_dashboard()
