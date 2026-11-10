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
    STAGE_COL,
    STAGE_TOURNAMENT,
    concat_responses,
    read_respondent_csv,
    read_responses_dir,
)
from dashboard import chart_theme as theme
from dashboard import hb_settings
from dashboard.exporting import download_workbook_button, render_chart
from dashboard.results_analysis import SurveyResults, analyze_survey_results

ROOT = Path(__file__).resolve().parent.parent

#: HB sampler settings baked into the client dashboard. The MCMC iteration count
#: and random seed are technical knobs, so they are not exposed in the UI. They
#: live in :mod:`dashboard.hb_settings` because the quality-diagnostics page has
#: to fit the same model with the same budget. The result is cached per dataset.
HB_ITERATIONS = hb_settings.HB_ITERATIONS
HB_SEED = hb_settings.HB_SEED


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


def load_context(
    spec_path: Path | str | None = None,
    workbook: Path | str | None = None,
) -> SurveyContext:
    """Resolve spec + Part A/C banks + label maps the same way the app does.

    Called with no arguments it resolves the spec and workbook from the
    environment, i.e. the product the dashboard was *launched* with. Passing an
    explicit ``spec_path`` / ``workbook`` builds the context for *that* product
    instead, so the page can follow the sidebar's product selection rather than
    being frozen on the launch default. An empty ``workbook`` (``None`` or
    ``""``) falls back to ``$SURVEY_WORKBOOK`` then the built-in default.
    """
    from conjoint import questionnaire as q
    from conjoint.acbc import respondent_sim as rs
    from conjoint.acbc.design import attribute_levels_from_spec
    from survey_views import section_source as ss

    spec = q.read_spec(spec_path or _spec_path())
    if not workbook:
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


def _question_prompt(ctx: SurveyContext, question_id: str) -> str:
    """Human-facing prompt for a Part A background question id."""
    for question in ctx.questions:
        if question.identifier == question_id:
            return question.prompt
    return question_id


# ---------------------------------------------------------------------------
# Unified export: one workbook holding every section's table
# ---------------------------------------------------------------------------
def _results_workbook_sheets(
    results: SurveyResults, ctx: SurveyContext
) -> "OrderedDict[str, pd.DataFrame]":
    """Assemble every section's table into ``{sheet_name: DataFrame}``.

    Single source for the "Download all results" workbook: one sheet per
    analysis output (importance, part-worths, WTP, purchase intent, segments,
    per-respondent utilities). The interactive market simulator is excluded:
    its shares depend on the user's live product configuration rather than
    being a fixed result.
    """
    from collections import OrderedDict

    sheets: "OrderedDict[str, pd.DataFrame]" = OrderedDict()

    importance = results.importance.copy()
    importance.insert(0, "Attribute", importance["attribute"].map(attr_name))
    sheets["Importance"] = importance

    sheets["Part-worth utilities"] = _partworths_long(results, ctx)[
        ["Attribute", "Level", "Utility"]
    ].round(3)

    if results.wtp is not None:
        sheets["WTP (stated)"] = pd.DataFrame(
            [
                {
                    "Feature": feature_label(ctx, feature_id),
                    "Modal band": band_label(ctx, fw.modal_band),
                    "Share willing to pay": fw.share_paid,
                    "Mean premium (USD)": fw.mean_usd,
                }
                for feature_id, fw in results.wtp.features.items()
            ]
        )

    derived = results.derived_wtp
    if derived.available and derived.per_attribute is not None:
        table = derived.per_attribute.copy()
        table["Attribute"] = table["attribute"].map(attr_name)
        table["Level"] = [
            level_label(ctx, a, lv) for a, lv in zip(table["attribute"], table["level"])
        ]
        sheets["WTP (derived)"] = table[["Attribute", "Level", "usd_vs_worst"]].rename(
            columns={"usd_vs_worst": "Value vs worst level (USD)"}
        )

    if results.calibration is not None:
        sheets["Purchase intent"] = pd.DataFrame(
            {
                "Purchase intent (0-5)": list(results.calibration.distribution.keys()),
                "Count": list(results.calibration.distribution.values()),
            }
        )

    if results.background is not None and results.background.questions:
        sheets["Segments"] = pd.DataFrame(
            [
                {"Question": _question_prompt(ctx, qid), "Answer": answer, "Count": count}
                for qid, counts in results.background.questions.items()
                for answer, count in counts.items()
            ]
        )

    sheets["HB utilities"] = results.hb_utilities

    return sheets


# ---------------------------------------------------------------------------
# Streamlit caching wrappers (thin; the core stays pure/testable)
# ---------------------------------------------------------------------------
def _cached_results(
    df: pd.DataFrame, spec_key: str, workbook_key: str, hb_iter: int, seed: int
) -> SurveyResults:
    import streamlit as st

    @st.cache_data(show_spinner="Fitting MNL + Hierarchical Bayes model…")
    def _run(frame: pd.DataFrame, spec: str, workbook: str, iters: int, s: int) -> SurveyResults:
        # ``spec``/``workbook`` are part of the cache key, so switching products
        # re-fits against the correct amount and price bands instead of reusing
        # the launch product's cached result.
        ctx = load_context(spec, workbook)
        return analyze_survey_results(
            frame,
            amount_bands=ctx.bands,
            price_labels=ctx.labels.get("price"),
            hb_iter=iters,
            seed=s,
        )

    return _run(df, spec_key, workbook_key, hb_iter, seed)


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
    st.caption(
        "To save a chart as an image, click the camera icon in its top-right toolbar. "
        "Use the \"Download all results\" button in the sidebar to export every section's table as a single Excel file."
    )

    loaded = _load_responses(st)
    if loaded is None:
        return
    df, source_dir = loaded

    # Resolve spec/labels/bands for the *selected* product, not the launch
    # default, so switching the sidebar "Product" dropdown re-labels every
    # section (attributes, price tiers, simulator) to match the chosen data.
    spec_key, workbook_key = _resolve_context_paths(source_dir)
    ctx = load_context(spec_key, workbook_key)

    try:
        results = _cached_results(df, spec_key, workbook_key, HB_ITERATIONS, HB_SEED)
    except Exception as exc:  # never crash the dashboard over a fit error
        st.error(f"Analysis failed: {exc}")
        return

    download_workbook_button(
        st.sidebar,
        _results_workbook_sheets(results, ctx),
        label="Download all results (Excel)",
        file_name="conjoint_results.xlsx",
        key="dl_all_results",
    )

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


#: Per-product questionnaire folders live under ``outputs/survey_responses_<product>``.
RESPONSES_DIR_PREFIX = "survey_responses_"


def _default_responses_dir() -> str:
    """The conventional per-product folder of collected questionnaires."""
    stem = _spec_path().stem.replace("questionnaire_spec", "").strip("_") or "default"
    return f"outputs/{RESPONSES_DIR_PREFIX}{stem}"


def _product_label(folder_name: str) -> str:
    """``survey_responses_computers`` → ``Computers`` (human-facing dropdown text)."""
    product = folder_name[len(RESPONSES_DIR_PREFIX):] or folder_name
    return product.replace("_", " ").title()


def _discover_response_dirs() -> list[tuple[str, str]]:
    """``(label, path)`` for every ``outputs/survey_responses_<product>`` folder present."""
    base = ROOT / "outputs"
    if not base.is_dir():
        return []
    return [
        (_product_label(path.name), f"outputs/{path.name}")
        for path in sorted(base.glob(f"{RESPONSES_DIR_PREFIX}*"))
        if path.is_dir()
    ]


# ---------------------------------------------------------------------------
# Product → survey context resolution
#
# The sidebar lets the user switch which product's responses to analyse, but
# the *context* (spec, attribute labels, WTP features, amount/price bands) is
# product-specific too. Resolving it from the chosen folder — rather than the
# fixed launch-time env vars — keeps the whole page in sync with the dropdown.
# ---------------------------------------------------------------------------
def _product_from_dir(folder: str | None) -> str | None:
    """``…/survey_responses_<product>`` → ``<product>`` (``None`` if it doesn't match)."""
    if not folder:
        return None
    name = Path(folder).name
    if not name.startswith(RESPONSES_DIR_PREFIX):
        return None  # free-form path / upload → keep the launch-time context
    return name[len(RESPONSES_DIR_PREFIX):] or None


def _spec_for_product(product: str | None) -> Path:
    """Per-product ``questionnaire_spec_<product>.json`` if present, else the env/default spec."""
    if product:
        candidate = ROOT / f"questionnaire_spec_{product}.json"
        if candidate.exists():
            return candidate
    return _spec_path()


def _workbook_for_product(product: str | None) -> Path | None:
    """Per-product Part A/C ``Survey_questions`` workbook for ``product``.

    Naming isn't uniform across products (``computer_survey_questions.xlsx`` for
    *computers*, the bare ``survey_questions.xlsx`` default for *smartphones*),
    so several conventional spellings are tried before the shared default. The
    env workbook is deliberately *not* used as a fallback here: it belongs to
    the launch product and must not leak across a product switch. With no
    product (uploads / free-form path) we defer to ``load_context``'s env logic.
    """
    if not product:
        return None
    singular = product[:-1] if product.endswith("s") else product
    candidates = (
        ROOT / f"{product}_survey_questions.xlsx",
        ROOT / f"{singular}_survey_questions.xlsx",
        ROOT / f"{product}.xlsx",
        ROOT / "survey_questions.xlsx",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_context_paths(folder: str | None) -> tuple[str, str]:
    """``(spec_key, workbook_key)`` for the product behind ``folder``.

    Returned as strings so they double as stable :func:`st.cache_data` keys; an
    empty ``workbook_key`` means "fall back to the env/default workbook".
    """
    product = _product_from_dir(folder)
    spec_path = _spec_for_product(product)
    workbook = _workbook_for_product(product)
    return str(spec_path), ("" if workbook is None else str(workbook))


def _pick_responses_dir(st) -> str:
    """Product dropdown over discovered folders (+ an 'Other folder…' text escape)."""
    discovered = _discover_response_dirs()
    other = "Other folder…"
    if not discovered:
        return st.sidebar.text_input("Responses folder", value=_default_responses_dir())

    paths = {label: path for label, path in discovered}
    choices = list(paths) + [other]
    default_path = _default_responses_dir()
    default_label = next(
        (label for label, path in discovered if path == default_path), choices[0]
    )
    picked = st.sidebar.selectbox(
        "Product",
        options=choices,
        index=choices.index(default_label),
        help="Pick which collected survey to analyse: one folder per product.",
    )
    if picked == other:
        return st.sidebar.text_input("Responses folder", value=default_path)
    return paths[picked]


def _load_responses(st) -> tuple[pd.DataFrame, str | None] | None:
    """Data-source picker → ``(frame, source_dir)`` (or ``None``).

    Reads the per-respondent ``responses_<id>.csv`` questionnaires the survey
    app produces — either a whole local folder of them or an ad-hoc upload of
    one or more. One file is one completed questionnaire. ``source_dir`` is the
    selected local folder (used to resolve the product's context) or ``None``
    for uploads, where the launch-time context is kept.
    """
    source = st.sidebar.radio(
        "Data source",
        ["Local responses folder", "Upload questionnaires"],
        help=(
            "Reads the per-respondent responses_<id>.csv files the survey app "
            "collects: a local folder of them, or an upload of one or more."
        ),
    )
    df: pd.DataFrame | None = None
    source_dir: str | None = None
    if source == "Local responses folder":
        folder = _pick_responses_dir(st)
        if not folder:
            st.info("Enter the folder holding the survey's responses_<id>.csv files.")
            return None
        try:
            df, files = read_responses_dir(folder)
        except Exception as exc:
            st.error(f"Could not read questionnaires: {exc}")
            return None
        source_dir = folder
        st.sidebar.caption(f"Loaded {len(files)} questionnaire(s) from `{folder}`.")
    else:  # Upload questionnaires
        uploaded = st.sidebar.file_uploader(
            "responses_<id>.csv files",
            type="csv",
            accept_multiple_files=True,
        )
        if not uploaded:
            st.info("Upload one or more responses_<id>.csv files in the sidebar.")
            return None
        try:
            df = concat_responses(*(read_respondent_csv(item, item.name) for item in uploaded))
        except Exception as exc:
            st.error(f"Could not read uploaded questionnaires: {exc}")
            return None
        st.sidebar.caption(f"Loaded {len(uploaded)} uploaded questionnaire(s).")

    if STAGE_COL not in df.columns or not (df[STAGE_COL] == STAGE_TOURNAMENT).any():
        st.error("These questionnaires contain no choice tasks, so the results cannot be computed.")
        return None
    return df, source_dir


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
        help="Largest Gelman-Rubin diagnostic across fitted utility coefficients; values below 1.1 indicate the Hierarchical Bayes model has converged.",
    )
    fg, bg = ("#16A34A", "#DCFCE7") if converged else ("#B45309", "#FEF3C7")
    label = "✓ Converged" if converged else "≈ Approximate (Rhat ≥ 1.1)"
    col3.markdown(
        f"<span style='background:{bg};color:{fg};padding:3px 12px;border-radius:999px;"
        f"font-size:0.8rem;font-weight:600;white-space:nowrap;'>{label}</span>",
        unsafe_allow_html=True,
    )


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
        color="relative_importance",
        color_continuous_scale=list(theme.SEQUENTIAL_INDIGO),
        text=imp["relative_importance"].map(lambda v: f"{v:.1%}"),
        title="Relative importance (Range_A / ΣRange)",
    )
    fig.update_layout(xaxis_tickformat=".0%", xaxis_title="", yaxis_title="")
    fig.update_coloraxes(showscale=False)  # the bar length already encodes magnitude
    theme.style_fig(fig)
    render_chart(st, fig, filename="attribute_importance")
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
        color="Utility",
        color_continuous_scale=list(theme.DIVERGING),
        color_continuous_midpoint=0,
        text=block["Utility"].map(lambda v: f"{v:+.0f}"),
        title=f"{attr_name(chosen)}: utility by level",
    )
    fig.update_layout(xaxis_title="", yaxis_title="")
    fig.update_coloraxes(showscale=False)  # coral = below-average level, teal = above
    theme.style_fig(fig)
    render_chart(st, fig, filename=f"partworths_{chosen}")
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
        st.markdown("**Stated WTP**: extra amount respondents say they pay")
        st.caption("Modal band = most frequently chosen extra-payment band.")
        if results.wtp is None:
            st.info("This dataset has no willingness-to-pay records.")
        else:
            rows = []
            for feature_id, fw in results.wtp.features.items():
                rows.append(
                    {
                        "Feature": feature_label(ctx, feature_id),
                        "Modal band": band_label(ctx, fw.modal_band),
                        "Share willing to pay": f"{fw.share_paid:.0%}",
                        "Mean premium ($)": (f"${fw.mean_usd:,.0f}" if fw.mean_usd is not None else "-"),
                    }
                )
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=300)
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
            fig = px.bar(
                dist,
                x="Band",
                y="Count",
                color="Count",
                color_continuous_scale=list(theme.SEQUENTIAL_INDIGO),
                title=feature_label(ctx, picked),
            )
            fig.update_layout(xaxis_title="", yaxis_title="")
            fig.update_coloraxes(showscale=False)
            theme.style_fig(fig)
            render_chart(st, fig, filename=f"wtp_bands_{picked}")

    with right:
        st.markdown("**Derived WTP**: dollar value from price part-worths")
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
                height=300,
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
    st.markdown('<span style="background:#1e6fd9;color:#fff;font-size:.66rem;font-weight:700;letter-spacing:.08em;border-radius:20px;padding:.1rem .55rem">INTERACTIVE</span> <b>Configure the products and see the predicted market shares</b>', unsafe_allow_html=True)
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
        color="Product",
        color_discrete_sequence=list(theme.PALETTE),
        text=share_df["Share"].map(lambda v: f"{v:.1%}"),
        title="Share of preference",
    )
    fig.update_layout(
        yaxis_tickformat=".0%", xaxis_title="", yaxis_title="", showlegend=False
    )
    theme.style_fig(fig)
    render_chart(st, fig, filename="share_of_preference")

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

    st.subheader("Purchase likelihood")
    cal = results.calibration
    if cal is None:
        st.info("This dataset has no purchase-likelihood records.")
        return
    col1, col2 = st.columns([1, 2])
    col1.metric("Mean purchase likelihood", f"{cal.mean_probability_pct:.0f}%", help="Purchase-intent rating from 0 to 5, converted to a percentage.")
    dist = pd.DataFrame(
        {"Purchase intent (0-5)": list(cal.distribution.keys()), "Count": list(cal.distribution.values())}
    )
    fig = px.bar(
        dist,
        x="Purchase intent (0-5)",
        y="Count",
        color="Purchase intent (0-5)",
        color_continuous_scale=list(theme.SEQUENTIAL_INDIGO),
        title="Purchase intent distribution (0 = never buy, 5 = definitely buy)",
    )
    fig.update_layout(xaxis_title="", yaxis_title="")
    fig.update_coloraxes(showscale=False)  # pale indigo = low intent, deep = high
    theme.style_fig(fig)
    render_chart(col2, fig, filename="purchase_intent")


# ---------------------------------------------------------------------------
# Section 7 — Respondent segments (Part A)
# ---------------------------------------------------------------------------
def _render_segments(st, results: SurveyResults, ctx: SurveyContext) -> None:
    import plotly.express as px

    st.subheader("Respondent segments")
    background = results.background
    if background is None or not background.questions:
        st.info("This dataset has no respondent background records.")
        return

    question_ids = list(background.questions.keys())
    picked = st.selectbox(
        "Select background question",
        options=question_ids,
        index=0,
        format_func=lambda qid: _question_prompt(ctx, qid),
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
        color="Answer",
        color_discrete_sequence=list(theme.PALETTE),
        title=_question_prompt(ctx, picked),
    )
    fig.update_layout(xaxis_title="", yaxis_title="", showlegend=False)
    theme.style_fig(fig)
    render_chart(st, fig, filename="respondent_segment")


if __name__ == "__main__":  # pragma: no cover — manual ``streamlit run``
    render_results_dashboard()
