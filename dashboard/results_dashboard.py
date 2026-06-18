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

    @st.cache_data(show_spinner="生成合成问卷数据中… / generating responses")
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

    @st.cache_data(show_spinner="拟合 MNL + HB 模型中… / fitting model")
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

    st.title("📊 ACBC 调研结果 / Conjoint Results")
    st.caption(
        "基于问卷 B4 选择拟合的 Hierarchical Bayes 部件效用,展示属性重要性、部件效用、"
        "支付意愿、市场模拟、购买可能性与受访者画像。"
    )

    ctx = load_context()
    df = _load_responses(st, ctx)
    if df is None:
        return

    hb_iter = int(
        st.sidebar.select_slider(
            "HB 迭代次数 / iterations",
            options=[200, 400, 1000, 2000, 4000],
            value=400,
            help="400 为预览档(Rhat 可能 > 1.1);出版级建议 ≥ 4000。",
        )
    )
    seed = int(st.sidebar.number_input("随机种子 / seed", value=0, step=1))

    try:
        results = _cached_results(df, hb_iter, seed)
    except Exception as exc:  # never crash the dashboard over a fit error
        st.error(f"分析失败 / analysis failed: {exc}")
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
        "数据来源 / data source",
        ["合成问卷数据", "上传 CSV", "本地路径"],
        help="需要 long-format acbc_responses.csv;默认实时生成一份合成问卷数据。",
    )
    df: pd.DataFrame | None = None
    if source == "合成问卷数据":
        n = int(st.sidebar.slider("受访者数量 / N", min_value=20, max_value=500, value=200, step=10))
        seed = int(st.sidebar.number_input("合成种子 / gen seed", value=2026, step=1))
        df = _cached_synthetic(n, seed)
        st.sidebar.download_button(
            "下载这份合成 CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="synthetic_responses.csv",
            mime="text/csv",
        )
    elif source == "上传 CSV":
        uploaded = st.sidebar.file_uploader("acbc_responses.csv", type="csv")
        if uploaded is None:
            st.info("请在左侧上传一个 long-format acbc_responses.csv。")
            return None
        df = pd.read_csv(uploaded)
    else:
        stem = _spec_path().stem.replace("questionnaire_spec", "").strip("_") or "default"
        default_path = f"outputs/synthetic_responses_{stem}.csv"
        path = st.sidebar.text_input("CSV 路径", value=default_path)
        if not path:
            return None
        try:
            df = read_acbc_responses(path)
        except Exception as exc:
            st.error(f"读取失败 / read failed: {exc}")
            return None

    if STAGE_COL not in df.columns or not (df[STAGE_COL] == STAGE_TOURNAMENT).any():
        st.error("该文件没有 tournament 行,无法做 ACBC 估计。")
        return None
    return df


# ---------------------------------------------------------------------------
# Section 1 — Overview
# ---------------------------------------------------------------------------
def _render_overview(st, results: SurveyResults) -> None:
    st.subheader("① 样本与收敛 / Overview")
    col1, col2, col3 = st.columns(3)
    col1.metric("受访者 / Respondents", f"{results.n_respondents}")
    col2.metric("Tournament 任务 / tasks", f"{results.n_tournament_tasks}")
    converged = results.rhat_max < 1.1
    col3.metric(
        "HB 收敛 Rhat max",
        f"{results.rhat_max:.2f}",
        help="Gelman-Rubin < 1.1 视为收敛。预览档迭代少时偏高,提高迭代次数即可。",
    )
    col3.caption("✅ 已收敛" if converged else "⚠️ 预览档(建议提高 HB 迭代次数)")


# ---------------------------------------------------------------------------
# Section 2 — Attribute importance
# ---------------------------------------------------------------------------
def _render_importance(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("② 属性重要性 / Attribute importance")
    imp = results.importance.copy()
    imp["属性"] = imp["attribute"].map(attr_name)
    imp = imp.sort_values("relative_importance")
    fig = px.bar(
        imp,
        x="relative_importance",
        y="属性",
        orientation="h",
        text=imp["relative_importance"].map(lambda v: f"{v:.1%}"),
        title="相对重要性 (Range_A / ΣRange)",
    )
    fig.update_layout(xaxis_tickformat=".0%", xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    top = imp.sort_values("relative_importance", ascending=False).iloc[0]
    st.caption(
        f"最重要的属性是 **{top['属性']}**(占 {top['relative_importance']:.1%}),"
        "条形越长代表该属性对选择的影响越大。"
    )


# ---------------------------------------------------------------------------
# Section 3 — Part-worth utilities
# ---------------------------------------------------------------------------
def _partworths_long(results: SurveyResults, ctx: SurveyContext) -> pd.DataFrame:
    rows = [
        {
            "attribute": attribute,
            "属性": attr_name(attribute),
            "level": level,
            "水平 / level": level_label(ctx, attribute, level),
            "效用 / utility": float(value),
        }
        for attribute, per_level in results.rescaled_utilities.items()
        for level, value in per_level.items()
    ]
    return pd.DataFrame(rows)


def _render_partworths(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("③ 部件效用 / Part-worth utilities")
    st.caption("零中心化「diffs」刻度(各属性平均极差=100),效用越高代表越受偏好。")
    tidy = _partworths_long(results, ctx)
    attributes = list(results.rescaled_utilities.keys())
    chosen = st.selectbox(
        "选择属性 / attribute",
        options=attributes,
        index=0,
        format_func=attr_name,
        key="pw_attribute",
    )
    block = tidy[tidy["attribute"] == chosen]
    fig = px.bar(
        block,
        x="效用 / utility",
        y="水平 / level",
        orientation="h",
        text=block["效用 / utility"].map(lambda v: f"{v:+.0f}"),
        title=f"{attr_name(chosen)} 各水平效用",
    )
    fig.update_layout(xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("查看全部属性的部件效用表"):
        st.dataframe(
            tidy[["属性", "水平 / level", "效用 / utility"]].round(1),
            hide_index=True,
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Section 4 — Willingness-to-pay
# ---------------------------------------------------------------------------
def _render_wtp(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("④ 支付意愿 / Willingness-to-pay")
    left, right = st.columns(2)

    with left:
        st.markdown("**陈述性 WTP(Part C)** — 受访者愿意为升级多付多少")
        if results.wtp is None:
            st.info("此数据没有 Part C(WTP)记录。")
        else:
            rows = []
            for feature_id, fw in results.wtp.features.items():
                rows.append(
                    {
                        "升级 / feature": feature_label(ctx, feature_id),
                        "最常见档位 / modal": band_label(ctx, fw.modal_band),
                        "愿意加价占比": f"{fw.share_paid:.0%}",
                        "平均加价 / mean $": (f"${fw.mean_usd:,.0f}" if fw.mean_usd is not None else "—"),
                    }
                )
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            feature_ids = list(results.wtp.features.keys())
            picked = st.selectbox(
                "查看某项升级的档位分布 / feature",
                options=feature_ids,
                index=0,
                format_func=lambda fid: feature_label(ctx, fid),
                key="wtp_feature",
            )
            fw = results.wtp.features[picked]
            dist = pd.DataFrame(
                {
                    "档位 / band": [band_label(ctx, code) for code in fw.band_counts],
                    "人数 / count": list(fw.band_counts.values()),
                }
            )
            fig = px.bar(dist, x="档位 / band", y="人数 / count", title=feature_label(ctx, picked))
            fig.update_layout(xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("**推导式 WTP** — 由价格部件效用换算的美元价值")
        derived = results.derived_wtp
        if not derived.available:
            st.info(f"无法推导货币化 WTP:{derived.note}。")
        else:
            st.caption(f"每 1 效用 ≈ **${derived.usd_per_util:,.0f}**(由价格档位斜率推得)。")
            table = derived.per_attribute.copy()
            table["属性"] = table["attribute"].map(attr_name)
            table["水平 / level"] = [
                level_label(ctx, a, lv) for a, lv in zip(table["attribute"], table["level"])
            ]
            table["相对最差水平的价值 / $"] = table["usd_vs_worst"].map(lambda v: f"${v:,.0f}")
            st.dataframe(
                table[["属性", "水平 / level", "相对最差水平的价值 / $"]],
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

    st.subheader("⑤ 市场模拟 / Market simulator")
    st.caption("配置若干竞争产品,基于每位受访者的 HB 效用计算 share-of-preference(偏好份额)。")

    n_products = int(st.number_input("产品数量 / products", min_value=2, max_value=4, value=2, step=1))
    attributes = list(ctx.attribute_levels.keys())
    products: dict[str, dict] = {}
    columns = st.columns(n_products)
    for index in range(n_products):
        default = _default_product_spec(ctx, index)
        name = f"产品 {chr(65 + index)}"
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
        {"产品 / product": list(shares.keys()), "份额 / share": list(shares.values())}
    )
    fig = px.bar(
        share_df,
        x="产品 / product",
        y="份额 / share",
        text=share_df["份额 / share"].map(lambda v: f"{v:.1%}"),
        title="偏好份额 / share of preference",
    )
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

    to_remove = st.multiselect(
        "移除产品看份额转移 / remove product(s)",
        options=list(products.keys()),
    )
    if to_remove and len(to_remove) < len(products):
        impact = sim.removal_impact(utilities, products, to_remove)
        transfer = impact.transfer.rename(
            columns={
                "product": "产品",
                "removed": "已移除",
                "share_before": "移除前",
                "share_after": "移除后",
                "delta": "变化",
            }
        )
        for column in ("移除前", "移除后", "变化"):
            transfer[column] = transfer[column].map(lambda v: f"{v:.1%}")
        st.dataframe(transfer, hide_index=True, use_container_width=True)
        st.caption("「变化」为正,表示该产品吸收了被移除产品的份额。")


# ---------------------------------------------------------------------------
# Section 6 — Purchase likelihood (B5 calibration)
# ---------------------------------------------------------------------------
def _render_calibration(st, results: SurveyResults) -> None:
    import plotly.express as px

    st.subheader("⑥ 购买可能性 / Purchase likelihood (B5)")
    cal = results.calibration
    if cal is None:
        st.info("此数据没有 B5 校准(calibration)记录。")
        return
    col1, col2 = st.columns([1, 2])
    col1.metric("平均购买可能性", f"{cal.mean_probability_pct:.0f}%", help="B5 概率 0–5,折算为百分比。")
    dist = pd.DataFrame(
        {"购买意愿 0–5": list(cal.distribution.keys()), "人数 / count": list(cal.distribution.values())}
    )
    fig = px.bar(dist, x="购买意愿 0–5", y="人数 / count", title="购买意愿分布(0=绝不买 · 5=一定买)")
    fig.update_layout(xaxis_title="", yaxis_title="")
    col2.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 7 — Respondent segments (Part A)
# ---------------------------------------------------------------------------
def _render_segments(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("⑦ 受访者画像 / Respondent segments (Part A)")
    background = results.background
    if background is None or not background.questions:
        st.info("此数据没有 Part A(背景)记录。")
        return

    def _prompt(question_id: str) -> str:
        for question in ctx.questions:
            if question.identifier == question_id:
                return question.prompt
        return question_id

    question_ids = list(background.questions.keys())
    picked = st.selectbox(
        "选择背景问题 / question",
        options=question_ids,
        index=0,
        format_func=_prompt,
        key="segment_question",
    )
    counts = background.questions[picked]
    dist = pd.DataFrame(
        {"选项 / answer": list(counts.keys()), "人数 / count": list(counts.values())}
    ).sort_values("人数 / count")
    fig = px.bar(
        dist,
        x="人数 / count",
        y="选项 / answer",
        orientation="h",
        title=_prompt(picked),
    )
    fig.update_layout(xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":  # pragma: no cover — manual ``streamlit run``
    render_results_dashboard()
