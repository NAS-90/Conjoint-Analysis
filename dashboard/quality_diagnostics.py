"""Dashboard page: ACBC data quality (§8) + model diagnostics (§9.10 #10).

Two layers:

* :func:`analyze_responses` — a **pure** function (no Streamlit) that fits the
  population MNL + HB, then assembles importance, rescaled part-worths, holdout
  hit-rate, price monotonicity, attribute dominance and per-respondent HB RLH
  into an :class:`AcbcAnalysis`. Unit-tested directly.
* :func:`render_quality_diagnostics` — the Streamlit view. The expensive fit is
  cached; the quality-flag sliders re-run only the cheap screen so the table
  updates live.

Data source defaults to the injected-pathology synthetic demo
(:mod:`conjoint.acbc.synthetic`); analysts can upload or point at a real
``acbc_responses.csv``.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from conjoint.acbc import diagnostics, estimate, quality, synthetic
from conjoint.acbc.responses import (
    RESPONDENT_COL,
    STAGE_COL,
    STAGE_TOURNAMENT,
    TASK_ID_COL,
    read_acbc_responses,
)

LevelUtilities = "OrderedDict[str, OrderedDict[str, float]]"


# ---------------------------------------------------------------------------
# Pure analysis core (testable without Streamlit)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AcbcAnalysis:
    """Everything the page needs from one fit of an ACBC response frame."""

    n_respondents: int
    n_tournament_tasks: int
    importance: pd.DataFrame
    level_utilities: "OrderedDict[str, OrderedDict[str, float]]"
    rescaled_utilities: "OrderedDict[str, OrderedDict[str, float]]"
    holdout: diagnostics.HoldoutResult
    dominance: diagnostics.DominanceResult
    monotonicity: diagnostics.MonotonicityResult | None
    rlh: pd.DataFrame
    rhat_max: float


def utilities_long(level_utilities: "OrderedDict[str, OrderedDict[str, float]]") -> pd.DataFrame:
    """Tidy ``(attribute, level, utility)`` frame for plotting part-worths."""
    rows = [
        {"attribute": attribute, "level": level, "utility": float(value)}
        for attribute, per_level in level_utilities.items()
        for level, value in per_level.items()
    ]
    return pd.DataFrame(rows, columns=["attribute", "level", "utility"])


def analyze_responses(
    df: pd.DataFrame,
    *,
    price_attribute: str = synthetic.PRICE_ATTRIBUTE,
    price_order: tuple[str, ...] = synthetic.PRICE_ORDER,
    hb_iter: int = 400,
    seed: int = 0,
) -> AcbcAnalysis:
    """Fit MNL + HB and assemble importance / diagnostics / per-respondent RLH.

    Pure and deterministic given ``seed`` — no Streamlit dependency, so it can
    be unit-tested and reused by the report exporter.
    """
    mnl = estimate.fit_from_responses(df)
    level_utilities = estimate.beta_to_level_utilities(
        mnl.beta, mnl.column_names, mnl.level_map
    )
    importance = estimate.attribute_importance(mnl)
    rescaled = estimate.rescale_zero_centered_diffs(level_utilities)
    holdout = diagnostics.holdout_hit_rate(df, seed=seed)
    dominance = diagnostics.dominant_attribute(importance)

    monotonicity = None
    if price_attribute in level_utilities and all(
        level in level_utilities[price_attribute] for level in price_order
    ):
        monotonicity = diagnostics.check_monotonicity(
            level_utilities, price_attribute, price_order, expect_decreasing=True
        )

    hb = estimate.fit_hb(
        df, n_iter=hb_iter, burn_in=hb_iter // 2, thinning=2, n_chains=2, seed=seed
    )
    rlh = estimate.per_respondent_rlh_hb(df, hb)

    tournament = df[df[STAGE_COL] == STAGE_TOURNAMENT]
    n_tasks = int(tournament.groupby([RESPONDENT_COL, TASK_ID_COL]).ngroups)
    return AcbcAnalysis(
        n_respondents=int(tournament[RESPONDENT_COL].nunique()),
        n_tournament_tasks=n_tasks,
        importance=importance,
        level_utilities=level_utilities,
        rescaled_utilities=rescaled,
        holdout=holdout,
        dominance=dominance,
        monotonicity=monotonicity,
        rlh=rlh,
        rhat_max=float(np.nanmax(hb.rhat)),
    )


# ---------------------------------------------------------------------------
# Streamlit view
# ---------------------------------------------------------------------------
def render_quality_diagnostics() -> None:
    """Render the ACBC quality + diagnostics page (called from ``app.py``)."""
    import streamlit as st

    st.title("ACBC data quality & diagnostics")
    st.caption(
        "§8 data cleaning + §9.10 model diagnostics. Defaults to synthetic demo "
        "data (with injected straight-lining / illogical / incomplete / speeding "
        "respondents); you can switch to a real acbc_responses.csv."
    )

    df = _load_responses(st)
    if df is None:
        return

    try:
        analysis = _cached_analysis(df)
    except Exception as exc:  # never crash the dashboard over a fit error
        st.error(f"Analysis failed: {exc}")
        return

    st.caption(
        f"Sample: {analysis.n_respondents} respondents · "
        f"{analysis.n_tournament_tasks} tournament tasks · "
        f"HB convergence Rhat max = {analysis.rhat_max:.3f}"
    )

    _render_diagnostic_cards(st, analysis)
    st.markdown("---")
    _render_importance(st, analysis)
    st.markdown("---")
    _render_quality_screen(st, df, analysis)


def _load_responses(st) -> pd.DataFrame | None:
    """Data-source picker → validated long-format frame (or ``None``)."""
    source = st.sidebar.radio(
        "Data source",
        ["Synthetic demo data", "Upload CSV", "Local path"],
        help="The new method needs a long-format acbc_responses.csv; defaults to synthetic data with injected issues.",
    )
    df: pd.DataFrame | None = None
    if source == "Synthetic demo data":
        seed = int(st.sidebar.number_input("Synthetic seed", value=2026, step=1))
        df = _cached_demo(seed)
        st.sidebar.download_button(
            "Download this synthetic CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="acbc_responses_demo.csv",
            mime="text/csv",
        )
    elif source == "Upload CSV":
        uploaded = st.sidebar.file_uploader("acbc_responses.csv", type="csv")
        if uploaded is None:
            st.info("Please upload a long-format acbc_responses.csv on the left.")
            return None
        df = pd.read_csv(uploaded)
    else:
        path = st.sidebar.text_input("CSV path", value="outputs/acbc_demo/acbc_responses.csv")
        if not path:
            return None
        try:
            df = read_acbc_responses(path)
        except Exception as exc:
            st.error(f"Read failed: {exc}")
            return None

    if STAGE_COL not in df.columns or not (df[STAGE_COL] == STAGE_TOURNAMENT).any():
        st.error("This file has no tournament rows, so ACBC estimation and diagnostics cannot run.")
        return None
    return df


def _render_diagnostic_cards(st, analysis: AcbcAnalysis) -> None:
    """Four headline diagnostics with pass/warn status."""
    st.subheader("Model diagnostics (§9.10 #10)")
    col1, col2, col3, col4 = st.columns(4)

    hit = analysis.holdout
    col1.metric(
        "Holdout hit-rate",
        f"{hit.hit_rate:.1%}",
        delta=f"{hit.hit_rate - hit.random_baseline:+.1%} vs random",
        help=f"Held out {hit.n_holdout_tasks} tasks, random baseline {hit.random_baseline:.1%}. Higher is better.",
    )
    col1.caption("Beats random" if hit.beats_random else "Not better than random")

    median_rlh = float(analysis.rlh["rlh"].median()) if not analysis.rlh.empty else float("nan")
    col2.metric("Median individual RLH", f"{median_rlh:.3f}", help="§9.6 computed with each respondent's β_i; near random level means poor answer quality.")

    if analysis.monotonicity is not None:
        ok = analysis.monotonicity.monotonic
        col3.metric("Price monotonicity", "Plausible" if ok else "Anomalous")
        col3.caption("Pricier → lower utility (expected)" if ok else f"Violations: {analysis.monotonicity.violations}")
    else:
        col3.metric("Price monotonicity", "—")
        col3.caption("No price attribute to check")

    dom = analysis.dominance
    col4.metric(
        "Max attribute share",
        f"{dom.relative_importance:.1%}",
        help=f"Most important attribute: {dom.attribute}. Above {dom.threshold:.0%} is treated as implausible dominance.",
    )
    col4.caption("Single attribute over-dominates" if dom.dominates else f"{dom.attribute} does not over-dominate")


def _render_importance(st, analysis: AcbcAnalysis) -> None:
    """Relative importance bar + raw/rescaled part-worth view."""
    import plotly.express as px

    st.subheader("Attribute importance & part-worths (§7 / §9.8)")
    left, right = st.columns([1, 1])

    with left:
        imp = analysis.importance.rename(
            columns={"attribute": "attribute", "relative_importance": "relative_importance"}
        ).sort_values("relative_importance", ascending=True)
        fig = px.bar(
            imp, x="relative_importance", y="attribute", orientation="h",
            title="Relative importance (Range_A / ΣRange)",
        )
        fig.update_layout(xaxis_tickformat=".0%", yaxis_title="", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        scale = st.radio(
            "Part-worth scale",
            ["raw (zero-centered)", "zero-centered diffs (mean range=100)"],
            horizontal=False,
            help="§9.8 readability transform; rescaled keeps relative importance unchanged, only scaling the mean range to 100.",
        )
        utilities = (
            analysis.level_utilities
            if scale.startswith("raw")
            else analysis.rescaled_utilities
        )
        tidy = utilities_long(utilities).sort_values(["attribute", "utility"])
        fig2 = px.bar(
            tidy, x="utility", y="level", color="attribute", orientation="h",
            title="Part-worths",
        )
        fig2.update_layout(yaxis_title="", xaxis_title="")
        st.plotly_chart(fig2, use_container_width=True)


def _render_quality_screen(st, df: pd.DataFrame, analysis: AcbcAnalysis) -> None:
    """§8 quality flags with live-tunable thresholds and an RLH cut."""
    import plotly.express as px

    st.subheader("Data quality screen (§8)")
    c1, c2, c3, c4 = st.columns(4)
    rlh_threshold = c1.slider("RLH removal threshold", 0.0, 1.0, 0.30, 0.01)
    speeding_quantile = c2.slider("Speeding percentile", 0.0, 0.49, 0.05, 0.01)
    min_tasks = c3.slider("Min tasks for straight-lining", 2, 12, 3, 1)
    max_incons = c4.slider("Illogical threshold (dominant-choice share)", 0.0, 1.0, 0.50, 0.05)

    has_duration = "duration" in df.columns
    flags = quality.screen_quality(
        df,
        level_utilities=analysis.level_utilities,
        duration_col="duration" if has_duration else None,
        thresholds=quality.QualityThresholds(
            min_tournament_tasks=min_tasks,
            speeding_quantile=speeding_quantile,
            max_inconsistent_fraction=max_incons,
        ),
    )
    low_rlh = set(analysis.rlh.loc[analysis.rlh["rlh"] < rlh_threshold, "respondent"])
    flags["low_rlh"] = flags[RESPONDENT_COL].isin(low_rlh)
    flags["exclude"] = flags["flagged"] | flags["low_rlh"]

    m1, m2, m3 = st.columns(3)
    m1.metric("§8 flagged", int(flags["flagged"].sum()))
    m2.metric(f"Low RLH (< {rlh_threshold:.2f})", int(flags["low_rlh"].sum()))
    m3.metric("Total flagged for removal", int(flags["exclude"].sum()), help="§8 flagged ∪ low RLH.")

    # RLH distribution with the cut + random baseline.
    if not analysis.rlh.empty:
        hist = px.histogram(analysis.rlh, x="rlh", nbins=20, title="Individual RLH distribution")
        hist.add_vline(x=rlh_threshold, line_dash="dash", line_color="red",
                       annotation_text="Removal threshold")
        hist.add_vline(x=analysis.holdout.random_baseline, line_dash="dot",
                       line_color="gray", annotation_text="Random baseline")
        st.plotly_chart(hist, use_container_width=True)

    only_flagged = st.checkbox("Show flagged respondents only", value=True)
    table = flags.merge(analysis.rlh[[RESPONDENT_COL, "rlh"]], on=RESPONDENT_COL, how="left")
    if only_flagged:
        table = table[table["exclude"]]
    display_cols = [
        RESPONDENT_COL, "n_tournament_tasks", "straightlining", "inconsistent_choices",
        "inconsistent_fraction", "incomplete", "speeding", "rlh", "low_rlh", "exclude",
    ]
    st.dataframe(
        table[display_cols].round({"inconsistent_fraction": 3, "rlh": 3}),
        hide_index=True, use_container_width=True,
    )
    st.download_button(
        "Download quality flags CSV",
        data=flags.to_csv(index=False).encode("utf-8"),
        file_name="acbc_quality_flags.csv",
        mime="text/csv",
    )
    if not has_duration:
        st.caption("Note: this data has no response duration, so the speeding check was skipped.")


# ---------------------------------------------------------------------------
# Streamlit caching wrappers (kept thin so the core stays pure/testable)
# ---------------------------------------------------------------------------
def _cached_demo(seed: int) -> pd.DataFrame:
    import streamlit as st

    @st.cache_data(show_spinner="Generating synthetic data…")
    def _gen(s: int) -> pd.DataFrame:
        return synthetic.generate_demo_responses(seed=s)

    return _gen(seed)


def _cached_analysis(df: pd.DataFrame) -> AcbcAnalysis:
    import streamlit as st

    @st.cache_data(show_spinner="Fitting MNL + HB model…")
    def _run(frame: pd.DataFrame) -> AcbcAnalysis:
        return analyze_responses(frame)

    return _run(df)
