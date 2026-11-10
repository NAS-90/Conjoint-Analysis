"""Munvest dashboard pages: introduction, portfolio overview, questionnaire guide, chart explanations."""
import os, glob
import pandas as pd
import streamlit as st

CSS = """
<style>
.mv-hero{padding:1.2rem 1.4rem;border:1px solid #243040;border-radius:12px;background:linear-gradient(135deg,#131a23,#0e141c);margin-bottom:1.2rem}
.mv-hero h2{margin:.1rem 0 .4rem;font-size:1.5rem}.mv-hero p{color:#b9c6d4;margin:0;line-height:1.55}
.mv-card{border:1px solid #243040;border-radius:12px;background:#131a23;padding:1rem 1.1rem;height:100%}
.mv-card h4{margin:0 0 .4rem;color:#9fdcff;font-size:1rem}.mv-card p,.mv-card li{color:#c8d3df;font-size:.9rem;line-height:1.5}
.mv-step{display:flex;gap:.9rem;margin:.55rem 0}.mv-step .n{flex:0 0 2rem;height:2rem;border-radius:50%;background:#1e6fd9;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center}
.mv-step b{color:#e8eef5}.mv-step span{color:#b9c6d4;font-size:.92rem}
.mv-explain{border-left:3px solid #4f9de8;background:#101822;border-radius:0 8px 8px 0;padding:.6rem .9rem;margin:.3rem 0 .8rem;font-size:.88rem;color:#c8d3df;line-height:1.5}
.mv-explain b{color:#9fdcff}
.mv-kpi{border:1px solid #243040;border-radius:10px;background:#131a23;padding:.7rem .9rem}.mv-kpi .v{font-size:1.6rem;font-weight:700;color:#e8eef5}.mv-kpi .l{font-size:.74rem;letter-spacing:.08em;text-transform:uppercase;color:#8fa1b5}
</style>
"""


def _css():
    st.markdown(CSS, unsafe_allow_html=True)


def explain(what, how=None):
    """Short 'what you see' box above a visualisation."""
    h = f"<b>What you see:</b> {what}"
    if how:
        h += f"<br><b>How to read it:</b> {how}"
    st.markdown(f'<div class="mv-explain">{h}</div>', unsafe_allow_html=True)


def _kpi(col, value, label):
    col.markdown(f'<div class="mv-kpi"><div class="v">{value}</div><div class="l">{label}</div></div>', unsafe_allow_html=True)


def _step(n, title, text):
    st.markdown(f'<div class="mv-step"><div class="n">{n}</div><div><b>{title}</b><br><span>{text}</span></div></div>', unsafe_allow_html=True)


def _card(col, title, body):
    col.markdown(f'<div class="mv-card"><h4>{title}</h4><p>{body}</p></div>', unsafe_allow_html=True)


def _header(sub):
    import munvest_theme as mv
    mv.apply(); _css(); mv.header(sub)


def intro_page(has_conjoint=False):
    _header("Portfolio Intelligence - Start here")
    st.markdown('<div class="mv-hero"><h2>Is your product portfolio working for your customers?</h2>'
                '<p>These tools show how similar your products really are, which ones compete with each other, '
                'where the market has white space &ndash; and, with conjoint analysis, what customers actually value. '
                'No statistics background needed: every chart comes with a short explanation.</p></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    _card(c1, "1 &middot; Distance analysis", "Measures how far apart your products are across all their features. Close products compete for the same customer (cannibalisation); large gaps are white space.")
    _card(c2, "2 &middot; Conjoint analysis", "A short survey in which customers choose between product variants. It reveals which features matter most, what customers will pay extra for, and how a new product would perform.")
    _card(c3, "3 &middot; Customer-weighted distance", "Combines both: features that customers care about count more. Two phones that look different on paper may still be near-identical for buyers &ndash; and vice versa.")
    st.markdown("### How to use the dashboards in 3 steps")
    _step(1, "Choose your data", "Use the sidebar on the left: pick a product category and, where offered, the view (Technical or Customer-weighted).")
    _step(2, "Start with the overview", "The <i>Portfolio Overview</i> page summarises every category: how many products are near-duplicates, which are unique, and where to look first.")
    _step(3, "Drill down and decide", "On the analysis pages pick a product, read the traffic-light assessment, explore the charts (each has a &lsquo;what you see&rsquo; box) and simulate removing products from the portfolio.")
    st.markdown("### Pages in this tool")
    pages = ["**Start here** &ndash; this introduction and glossary",
             "**Portfolio Overview** &ndash; structured summary across all categories",
             "**Distance Analysis** &ndash; product-level neighbours, alerts, product maps, removal simulation"]
    if has_conjoint:
        pages.insert(2, "**Conjoint Results** &ndash; attribute importance, part-worths, willingness to pay, market simulator, segments")
    pages.append("**Build your own study** &ndash; step-by-step guide to preparing product data" + (" and a survey questionnaire" if has_conjoint else ""))
    st.markdown("\n".join(f"- {p}" for p in pages), unsafe_allow_html=True)
    with st.expander("Glossary &ndash; key terms in plain language"):
        st.markdown("""
- **Distance**: a number describing how different two products are across all (standardised) features. 0 = identical; larger = more different.
- **Nearest neighbour**: the product closest to a given one &ndash; its most direct substitute.
- **Cannibalisation**: two of your own products are so similar that they take sales from each other.
- **White space**: a gap in the portfolio where no product serves a customer need.
- **Product map (PCA)**: a 2D/3D picture that squeezes many features into a few axes while keeping similar products together.
- **Attribute importance**: how strongly a feature (e.g. price, battery) influences customer choice, in percent.
- **Part-worth utility**: the appeal of one specific level of a feature (e.g. 16 GB RAM) relative to the others.
- **Willingness to pay (WTP)**: the extra amount customers would pay for an upgrade.
- **Hierarchical Bayes (HB)**: the statistical model that estimates preferences per respondent from a small number of choices.
""")
    st.caption("All data shown are demonstration data. Your own data can be loaded as described under 'Build your own study'.")
    import munvest_theme as mv; mv.footer()


def _load_categories():
    cats = {}
    for d in sorted(glob.glob("outputs/*/")):
        name = os.path.basename(os.path.dirname(d))
        nn = os.path.join(d, "nearest_neighbors.csv")
        if name.startswith("survey_responses") or not os.path.exists(nn):
            continue
        try:
            df = pd.read_csv(nn)
        except Exception:
            continue
        if len(df) and df.shape[1] >= 4:
            cats[name] = df
    return cats


def _label(n):
    return {"conjoint_demo": "Tractors (conjoint demo)"}.get(n, n.replace("_", " ").title())


def overview_page(has_conjoint=False):
    import plotly.graph_objects as go
    _header("Portfolio Overview")
    st.title("Portfolio overview")
    st.caption("One page, every category: how crowded is each portfolio and where should you look first?")
    cats = _load_categories()
    if not cats:
        st.info("No analysis data available yet.")
        return
    rows = []
    for name, df in cats.items():
        r1 = df[df.iloc[:, 1] == 1].copy()
        r1["d"] = r1.iloc[:, 3].astype(float)
        pos = r1[r1.d > 0]["d"]
        t1, t2 = (float(pos.quantile(.10)), float(pos.quantile(.50))) if len(pos) >= 10 else (0.05, 0.5)
        n_c = int((r1.d < t1).sum()); n_o = int(((r1.d >= t1) & (r1.d < t2)).sum()); n_u = int((r1.d >= t2).sum())
        closest = r1.sort_values("d").iloc[0]; unique = r1.sort_values("d").iloc[-1]
        rows.append(dict(name=name, products=r1.iloc[:, 0].nunique(), median=float(r1.d.median()), c=n_c, o=n_o, u=n_u,
                         pair=f"{closest.iloc[0]}  ↔  {closest.iloc[2]}", pd=float(closest.d), uniq=str(unique.iloc[0]), ud=float(unique.d)))
    k = st.columns(4)
    _kpi(k[0], len(rows), "Categories analysed")
    _kpi(k[1], f"{sum(r['products'] for r in rows):,}", "Products in total")
    _kpi(k[2], sum(r["c"] for r in rows), "Cannibalisation candidates")
    _kpi(k[3], sum(r["u"] for r in rows), "Clearly unique products")
    st.markdown("### Portfolio health by category")
    explain("For each category the products are split into three groups by the distance to their closest sibling: "
            "<b>cannibalisation risk</b> (nearly identical), <b>overlap</b> (similar) and <b>unique</b>.",
            "Longer red/amber segments mean a more crowded portfolio. The split is relative to each portfolio (closest 10% / median), so categories are comparable in structure, not in absolute distance.")
    fig = go.Figure()
    labels = [_label(r["name"]) for r in rows]
    for key, nm, col in (("c", "Cannibalisation risk", "#ff8a80"), ("o", "Overlap", "#e8b24a"), ("u", "Unique", "#6fd3a5")):
        tot = [max(1, r["products"]) for r in rows]
        fig.add_bar(y=labels, x=[r[key] / t * 100 for r, t in zip(rows, tot)], name=nm, orientation="h", marker_color=col,
                    text=[r[key] for r in rows], textposition="inside")
    fig.update_layout(barmode="stack", height=120 + 60 * len(rows), xaxis_title="% of products", margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.15))
    import munvest_theme as mv
    st.plotly_chart(mv.plotly_dark(fig), use_container_width=True)
    st.markdown("### Key findings per category")
    explain("A summary row per category with the most similar pair and the most distinctive product.", "Start your review with the most similar pair: it is the strongest candidate for consolidation.")
    tbl = pd.DataFrame([{"Category": _label(r["name"]), "Products": r["products"], "Median gap to closest sibling": round(r["median"], 2),
                         "Most similar pair": r["pair"], "Pair distance": round(r["pd"], 3), "Most distinctive product": r["uniq"]} for r in rows])
    st.dataframe(tbl, hide_index=True, use_container_width=True)
    if has_conjoint:
        _conjoint_block()
    st.markdown("### Where to go next")
    st.markdown("- **Distance Analysis**: pick one of the products above and see its neighbours, alert and product map.\n"
                + ("- **Conjoint Results**: see what customers value and simulate market shares.\n" if has_conjoint else "")
                + "- **Build your own study**: load your portfolio" + (" and run your own survey." if has_conjoint else "."))
    mv.footer()


def _conjoint_block():
    st.markdown("### Customer view: technical vs. customer-weighted")
    p_t, p_w = "outputs/conjoint_demo/nearest_neighbors.csv", "outputs/conjoint_demo/nearest_neighbors_weighted.csv"
    imp = "outputs/conjoint_demo/importance.csv"
    c1, c2 = st.columns(2)
    with c1:
        if os.path.exists(imp):
            import plotly.graph_objects as go, munvest_theme as mv
            d = pd.read_csv(imp).sort_values("relative_importance", ascending=False).head(8)
            explain("The features customers weight most when comparing products (reference study weights).", "Longer bar = the feature changes customer choice more. These weights re-scale the distance in the customer-weighted view.")
            fig = go.Figure(go.Bar(y=d["attribute"][::-1], x=d["relative_importance"][::-1] * (100 if d["relative_importance"].max() <= 1.0 else 1), orientation="h", marker_color="#4f9de8"))
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Relative importance (%)")
            st.plotly_chart(mv.plotly_dark(fig), use_container_width=True)
    with c2:
        if os.path.exists(p_t) and os.path.exists(p_w):
            a = pd.read_csv(p_t); b = pd.read_csv(p_w)
            a1 = a[a.iloc[:, 1] == 1].set_index(a.columns[0]).iloc[:, 1]; b1 = b[b.iloc[:, 1] == 1].set_index(b.columns[0]).iloc[:, 1]
            j = a1.to_frame("t").join(b1.to_frame("w"), how="inner")
            ch = int((j.t != j.w).sum())
            explain("How often the closest substitute changes once customer preferences are taken into account.", "A high share means technical specs alone mislead: customers see the portfolio differently from the datasheet.")
            _kpi(st, f"{ch} of {len(j)}", "products with a different closest substitute")
            st.caption(f"{ch/len(j)*100:.0f}% of products change their nearest neighbour in the customer-weighted view.")


def guide_page(has_conjoint=False):
    _header("Build your own study")
    st.title("Build your own study" if has_conjoint else "Use your own product data")
    st.caption("A step-by-step guide. Allow about 30 minutes for the first run; later studies take minutes.")
    st.markdown("### The process at a glance")
    steps = [("Prepare the product workbook", "One Excel file with your products and their features.")]
    if has_conjoint:
        steps += [("Create the questionnaire", "A second Excel file with background questions and willingness-to-pay items."),
                  ("Collect responses", "Share the survey link; every respondent downloads one response file."),
                  ("Analyse", "Load the responses: importance, part-worths, market simulator and customer-weighted distance.")]
    else:
        steps += [("Run the distance calculation", "Two short commands create the distance matrix and nearest neighbours."),
                  ("Open the dashboard", "Pick your category in the sidebar and explore.")]
    for i, (t, x) in enumerate(steps, 1):
        _step(i, t, x)
    st.markdown("### Step 1 &middot; Prepare the product workbook")
    st.markdown("Create an Excel file with **two sheets**:")
    c1, c2 = st.columns(2)
    _card(c1, "Sheet <code>Edited</code> &ndash; your data", "One row per product. First column <code>product_id</code> (unique name), then one column per feature (price, weight, brand, &hellip;).")
    _card(c2, "Sheet <code>Feature_data</code> &ndash; the dictionary", "One row per column of <code>Edited</code>, describing how to treat it (type, direction, importance, units, conjoint levels).")
    explain("The columns of <code>Feature_data</code>.", "Fill one row per feature; dropdowns in the template help with the allowed values.")
    spec = pd.DataFrame([
        ("feature_name", "Exact column name in <i>Edited</i>", "price"),
        ("description", "Plain-language explanation", "Retail price"),
        ("data_types", "text, nominal (categories), metric (numbers)", "metric"),
        ("included_in_analysis", "yes / no &ndash; whether the feature enters the distance", "yes"),
        ("normalization_method", "How values are put on a common scale", "z-score"),
        ("ideal_direction", "higher, lower or neutral &ndash; what customers prefer", "lower"),
        ("weight_importance", "Technical weight: low / medium / high", "high"),
        ("unit, value_min, value_max", "Unit and valid range (optional, used for cleaning)", "EUR, 1000, 300000"),
        ("conjoint_role", "identifier, attribute (asked in the survey) or skip", "attribute"),
        ("conjoint_levels", "Levels shown to respondents, separated by semicolons", "basic; standard; premium"),
        ("conjoint_level_codes", "Matching codes for the levels", "basic; standard; premium"),
    ], columns=["Column", "Meaning", "Example"])
    st.markdown(spec.to_html(escape=False, index=False, classes="mv-t"), unsafe_allow_html=True)
    st.markdown("""<style>table.mv-t{width:100%;border-collapse:collapse;font-size:.86rem}table.mv-t th{text-align:left;color:#8fa1b5;border-bottom:1px solid #243040;padding:.4rem}table.mv-t td{padding:.4rem;border-bottom:1px solid #1b2430;color:#c8d3df}</style>""", unsafe_allow_html=True)
    _dl("Download product workbook template", "templates/feature_schema_template.xlsx", "templates/custom_product_template.xlsx")
    if has_conjoint:
        st.markdown("### Step 2 &middot; Create the questionnaire")
        st.markdown("The survey is generated from your workbook automatically &ndash; every feature with <code>conjoint_role = attribute</code> becomes part of the choice tasks. "
                    "What you add is the <b>question workbook</b> with background and willingness-to-pay questions:", unsafe_allow_html=True)
        qs = pd.DataFrame([
            ("section", "A = background question, C = upgrade for willingness to pay, bands = price bands for C", "A"),
            ("id", "Short unique name", "budget"),
            ("prompt", "The question as respondents read it", "Roughly what budget do you have in mind?"),
            ("input_type", "single (one answer) or multi (several)", "single"),
            ("options", "Answer options separated by semicolons", "Under $600; $600 - $1 200; Over $1 200"),
            ("help", "Optional hint under the question", "Choose all that apply."),
        ], columns=["Column", "Meaning", "Example"])
        explain("The columns of the sheet <code>Survey_questions</code>.", "Add as many section A questions as you need; keep section C to about six upgrades.")
        st.markdown(qs.to_html(escape=False, index=False, classes="mv-t"), unsafe_allow_html=True)
        _dl("Download question workbook template", "survey_setup_bundle/Input_template/survey_questions_template.xlsx")
        st.markdown("**What respondents experience** (about 8&ndash;10 minutes):")
        flow = pd.DataFrame([
            ("Welcome", "Purpose and optional respondent ID"), ("Part A", "Background: purchase timing, budget, usage"),
            ("B0", "Features and levels explained"), ("B2", "Must-haves and no-goes (screening)"),
            ("B4", "8 choice tasks: Option A vs. Option B"), ("B5", "Purchase probability 0&ndash;5 for three concepts"),
            ("Part C", "Willingness to pay for upgrades"), ("Thank you", "Respondent downloads and sends the response file")],
            columns=["Stage", "What happens"])
        st.markdown(flow.to_html(escape=False, index=False, classes="mv-t"), unsafe_allow_html=True)
        st.markdown("### Step 3 &middot; Collect responses")
        _step(1, "Start the survey app", "Locally: <code>SURVEY_SPEC=questionnaire_spec.json SURVEY_WORKBOOK=survey_questions.xlsx streamlit run survey.py</code>. For customers, deploy <code>survey.py</code> on Streamlit Community Cloud and share the link.")
        _step(2, "Each respondent sends one file", "<code>responses_&lt;id&gt;.csv</code>, produced by the &lsquo;Send my responses&rsquo; button.")
        _step(3, "Aim for 30&ndash;50 respondents or more", "More respondents give stabler importance and willingness-to-pay values. Check the HB convergence indicator on the results page.")
        st.markdown("### Step 4 &middot; Analyse")
        _step(1, "Load the files", "Place them in <code>outputs/survey_responses_&lt;product&gt;/</code> or use <i>Upload questionnaires</i> in the sidebar of <i>Conjoint Results</i>.")
        _step(2, "Read the results", "Attribute importance, part-worths, willingness to pay, market simulator, purchase likelihood and segments appear automatically; the Excel export contains every table.")
        _step(3, "Feed the weights into the distance analysis", "<code>python -m conjoint.acbc.estimate --responses acbc_responses.csv --out-importance importance.csv</code>, then <code>python compute_distance_matrix.py --mode weighted --importance importance.csv --attribute-map attribute_column_map.json</code>.")
    else:
        st.markdown("### Step 2 &middot; Calculate distances")
        _step(1, "Preprocess", "<code>python preprocessing.py --excel your_file.xlsx</code>")
        _step(2, "Compute the distance matrix", "<code>python compute_distance_matrix.py --excel your_file.xlsx</code>, then move the generated CSVs into <code>outputs/your_dataset/</code>.")
        _step(3, "Open the dashboard", "Your dataset appears in the category list. Customer-weighted views and surveys are available in the Conjoint tool: <a href='https://munvest-conjoint.streamlit.app' target='_blank'>munvest-conjoint.streamlit.app</a>.")
    st.markdown("### Tips for good results")
    st.markdown("- Use **4&ndash;8 attributes** with 2&ndash;5 levels each; include price as an attribute for willingness-to-pay.\n- Describe levels in customer language, not internal jargon.\n- Use unique, readable product IDs &ndash; they appear in every chart.\n- Need help? Contact Munvest via <a href='https://munvest.com' target='_blank'>munvest.com</a>.", unsafe_allow_html=True)
    import munvest_theme as mv; mv.footer()


def _dl(label, *paths):
    path = next((x for x in paths if os.path.exists(x)), None)
    if path:
        with open(path, "rb") as f:
            st.download_button(label, f.read(), file_name=os.path.basename(path), key="dl_" + path)


def route(name, file):
    """Turn a plain app.py into a multipage app (returns True if the router ran)."""
    if name != "__main__":
        return False
    import runpy
    def intro(): intro_page(False)
    def overview(): overview_page(False)
    def distance(): runpy.run_path(file, run_name="__distance__")
    def guide(): guide_page(False)
    pg = st.navigation([
        st.Page(intro, title="Start here", default=True),
        st.Page(overview, title="Portfolio Overview", url_path="overview"),
        st.Page(distance, title="Distance Analysis", url_path="distance"),
        st.Page(guide, title="Use your own data", url_path="guide"),
    ])
    pg.run()
    return True
