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

    st.title("📋 ACBC 数据质量与诊断")
    st.caption(
        "§8 数据清洗 + §9.10 模型诊断。默认使用合成 demo 数据(已注入直线作答 / "
        "不合逻辑 / 未完成 / 速答 四类问题受访者),可改用真实 acbc_responses.csv。"
    )

    df = _load_responses(st)
    if df is None:
        return

    try:
        analysis = _cached_analysis(df)
    except Exception as exc:  # never crash the dashboard over a fit error
        st.error(f"分析失败:{exc}")
        return

    st.caption(
        f"样本:{analysis.n_respondents} 位受访者 · "
        f"{analysis.n_tournament_tasks} 个 tournament 任务 · "
        f"HB 收敛 Rhat max = {analysis.rhat_max:.3f}"
    )

    _render_diagnostic_cards(st, analysis)
    st.markdown("---")
    _render_importance(st, analysis)
    st.markdown("---")
    _render_quality_screen(st, df, analysis)


def _load_responses(st) -> pd.DataFrame | None:
    """Data-source picker → validated long-format frame (or ``None``)."""
    source = st.sidebar.radio(
        "数据来源",
        ["合成 demo 数据", "上传 CSV", "本地路径"],
        help="新方法需要 long-format acbc_responses.csv;默认用注入问题的合成数据。",
    )
    df: pd.DataFrame | None = None
    if source == "合成 demo 数据":
        seed = int(st.sidebar.number_input("合成种子", value=2026, step=1))
        df = _cached_demo(seed)
        st.sidebar.download_button(
            "下载这份合成 CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="acbc_responses_demo.csv",
            mime="text/csv",
        )
    elif source == "上传 CSV":
        uploaded = st.sidebar.file_uploader("acbc_responses.csv", type="csv")
        if uploaded is None:
            st.info("请在左侧上传一个 long-format acbc_responses.csv。")
            return None
        df = pd.read_csv(uploaded)
    else:
        path = st.sidebar.text_input("CSV 路径", value="outputs/acbc_demo/acbc_responses.csv")
        if not path:
            return None
        try:
            df = read_acbc_responses(path)
        except Exception as exc:
            st.error(f"读取失败:{exc}")
            return None

    if STAGE_COL not in df.columns or not (df[STAGE_COL] == STAGE_TOURNAMENT).any():
        st.error("该文件没有 tournament 行,无法做 ACBC 估计与诊断。")
        return None
    return df


def _render_diagnostic_cards(st, analysis: AcbcAnalysis) -> None:
    """Four headline diagnostics with pass/warn status."""
    st.subheader("模型诊断 (§9.10 #10)")
    col1, col2, col3, col4 = st.columns(4)

    hit = analysis.holdout
    col1.metric(
        "Holdout 命中率",
        f"{hit.hit_rate:.1%}",
        delta=f"{hit.hit_rate - hit.random_baseline:+.1%} vs 随机",
        help=f"留出 {hit.n_holdout_tasks} 个任务,随机基线 {hit.random_baseline:.1%}。越高越好。",
    )
    col1.caption("✅ 优于随机" if hit.beats_random else "⚠️ 不优于随机")

    median_rlh = float(analysis.rlh["rlh"].median()) if not analysis.rlh.empty else float("nan")
    col2.metric("个体 RLH 中位数", f"{median_rlh:.3f}", help="§9.6 用各自 β_i 计算;接近随机水平说明作答质量差。")

    if analysis.monotonicity is not None:
        ok = analysis.monotonicity.monotonic
        col3.metric("价格单调性", "✅ 合理" if ok else "❌ 异常")
        col3.caption("越贵效用越低(预期)" if ok else f"违反:{analysis.monotonicity.violations}")
    else:
        col3.metric("价格单调性", "—")
        col3.caption("无 price 属性可检查")

    dom = analysis.dominance
    col4.metric(
        "最大属性占比",
        f"{dom.relative_importance:.1%}",
        help=f"最重要属性:{dom.attribute}。超过 {dom.threshold:.0%} 视为不合理支配。",
    )
    col4.caption("❌ 单属性过度支配" if dom.dominates else f"✅ {dom.attribute} 未过度支配")


def _render_importance(st, analysis: AcbcAnalysis) -> None:
    """Relative importance bar + raw/rescaled part-worth view."""
    import plotly.express as px

    st.subheader("属性重要性与部件效用 (§7 / §9.8)")
    left, right = st.columns([1, 1])

    with left:
        imp = analysis.importance.rename(
            columns={"attribute": "attribute", "relative_importance": "relative_importance"}
        ).sort_values("relative_importance", ascending=True)
        fig = px.bar(
            imp, x="relative_importance", y="attribute", orientation="h",
            title="相对重要性 (Range_A / ΣRange)",
        )
        fig.update_layout(xaxis_tickformat=".0%", yaxis_title="", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        scale = st.radio(
            "部件效用刻度",
            ["raw (zero-centered)", "zero-centered diffs (mean range=100)"],
            horizontal=False,
            help="§9.8 可读性变换;rescaled 保持相对重要性不变,只是把平均极差缩放到 100。",
        )
        utilities = (
            analysis.level_utilities
            if scale.startswith("raw")
            else analysis.rescaled_utilities
        )
        tidy = utilities_long(utilities).sort_values(["attribute", "utility"])
        fig2 = px.bar(
            tidy, x="utility", y="level", color="attribute", orientation="h",
            title="部件效用 (part-worths)",
        )
        fig2.update_layout(yaxis_title="", xaxis_title="")
        st.plotly_chart(fig2, use_container_width=True)


def _render_quality_screen(st, df: pd.DataFrame, analysis: AcbcAnalysis) -> None:
    """§8 quality flags with live-tunable thresholds and an RLH cut."""
    import plotly.express as px

    st.subheader("数据质量筛查 (§8)")
    c1, c2, c3, c4 = st.columns(4)
    rlh_threshold = c1.slider("RLH 剔除阈值", 0.0, 1.0, 0.30, 0.01)
    speeding_quantile = c2.slider("speeding 分位", 0.0, 0.49, 0.05, 0.01)
    min_tasks = c3.slider("直线作答最少任务数", 2, 12, 3, 1)
    max_incons = c4.slider("不合逻辑阈值 (支配选择占比)", 0.0, 1.0, 0.50, 0.05)

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
    m1.metric("§8 被标记", int(flags["flagged"].sum()))
    m2.metric(f"低 RLH (< {rlh_threshold:.2f})", int(flags["low_rlh"].sum()))
    m3.metric("建议剔除合计", int(flags["exclude"].sum()), help="§8 标记 ∪ 低 RLH。")

    # RLH distribution with the cut + random baseline.
    if not analysis.rlh.empty:
        hist = px.histogram(analysis.rlh, x="rlh", nbins=20, title="个体 RLH 分布")
        hist.add_vline(x=rlh_threshold, line_dash="dash", line_color="red",
                       annotation_text="剔除阈值")
        hist.add_vline(x=analysis.holdout.random_baseline, line_dash="dot",
                       line_color="gray", annotation_text="随机基线")
        st.plotly_chart(hist, use_container_width=True)

    only_flagged = st.checkbox("只看被标记的受访者", value=True)
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
        "下载质量旗标 CSV",
        data=flags.to_csv(index=False).encode("utf-8"),
        file_name="acbc_quality_flags.csv",
        mime="text/csv",
    )
    if not has_duration:
        st.caption("注:该数据未采集作答时长,speeding 检查已跳过。")


# ---------------------------------------------------------------------------
# Streamlit caching wrappers (kept thin so the core stays pure/testable)
# ---------------------------------------------------------------------------
def _cached_demo(seed: int) -> pd.DataFrame:
    import streamlit as st

    @st.cache_data(show_spinner="生成合成数据中…")
    def _gen(s: int) -> pd.DataFrame:
        return synthetic.generate_demo_responses(seed=s)

    return _gen(seed)


def _cached_analysis(df: pd.DataFrame) -> AcbcAnalysis:
    import streamlit as st

    @st.cache_data(show_spinner="拟合 MNL + HB 模型中…")
    def _run(frame: pd.DataFrame) -> AcbcAnalysis:
        return analyze_responses(frame)

    return _run(df)
