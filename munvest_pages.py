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
.mv-pill{display:inline-block;background:#1e6fd9;color:#fff;font-size:.66rem;font-weight:700;letter-spacing:.08em;border-radius:20px;padding:.1rem .55rem;margin-right:.3rem}.mv-pill-off{display:inline-block;border:1px solid #2c3a4c;color:#8fa1b5;font-size:.66rem;letter-spacing:.08em;border-radius:20px;padding:.05rem .5rem}
.mv-agenda{border:1px solid #243040;border-radius:10px;background:#101822;padding:.7rem 1rem;margin:.6rem 0 1.2rem}.mv-ag-t{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:#8fa1b5;margin-bottom:.3rem}.mv-agenda table{width:100%;border-collapse:collapse;font-size:.86rem}.mv-agenda td{padding:.3rem .5rem;border-top:1px solid #1b2430;color:#c8d3df;vertical-align:top}.mv-agenda td:first-child{color:#8fa1b5;width:1.5rem}
.mv-note{border:1px solid #6b5a22;background:#1d1a0f;border-radius:10px;padding:.7rem 1rem;color:#e6d9a8;font-size:.9rem;margin:.8rem 0}.mv-cta{border:1px solid #1e6fd9;background:linear-gradient(135deg,#102036,#0e1a2b);border-radius:12px;padding:1.1rem 1.3rem;margin:1.2rem 0}.mv-cta h3{margin:0 0 .3rem}.mv-cta a.b{display:inline-block;margin-top:.6rem;background:#1e6fd9;color:#fff!important;padding:.45rem 1.1rem;border-radius:6px;font-weight:600;text-decoration:none}
.mv-kpi{border:1px solid #243040;border-radius:10px;background:#131a23;padding:.7rem .9rem}.mv-kpi .v{font-size:1.6rem;font-weight:700;color:#e8eef5}.mv-kpi .l{font-size:.74rem;letter-spacing:.08em;text-transform:uppercase;color:#8fa1b5}
</style>
"""


def _css():
    st.markdown(CSS, unsafe_allow_html=True)


def explain(what, how=None, interactive=None):
    """Short 'what you see' box above a visualisation; optional INTERACTIVE marker."""
    h = f"<b>What you see:</b> {what}"
    if how:
        h += f"<br><b>How to read it:</b> {how}"
    if interactive:
        h = f'<span class="mv-pill">INTERACTIVE</span> <b>{interactive}</b><br>' + h
    st.markdown(f'<div class="mv-explain">{h}</div>', unsafe_allow_html=True)


def agenda(items):
    """Sub-agenda for a page: items = [(section, description, interactive_bool)]."""
    rows = "".join(f'<tr><td>{i}</td><td><b>{a}</b></td><td>{b}</td><td>{"<span class=mv-pill>INTERACTIVE</span>" if c else "<span class=mv-pill-off>read-only</span>"}</td></tr>' for i, (a, b, c) in enumerate(items, 1))
    st.markdown(f'<div class="mv-agenda"><div class="mv-ag-t">On this page</div><table>{rows}</table></div>', unsafe_allow_html=True)


def _kpi(col, value, label):
    col.markdown(f'<div class="mv-kpi"><div class="v">{value}</div><div class="l">{label}</div></div>', unsafe_allow_html=True)


def _step(n, title, text):
    st.markdown(f'<div class="mv-step"><div class="n">{n}</div><div><b>{title}</b><br><span>{text}</span></div></div>', unsafe_allow_html=True)


def _card(col, title, body):
    col.markdown(f'<div class="mv-card"><h4>{title}</h4><p>{body}</p></div>', unsafe_allow_html=True)


def _header(sub):
    import munvest_theme as mv
    mv.apply(); _css(); mv.header(sub)


TOOLS = {
    "conjoint": dict(name="Conjoint Analysis", other="Distance Analysis"),
    "distance": dict(name="Distance Analysis", other="Conjoint Analysis"),
}
CONTACT = "https://munvest.com"


def _cta(text):
    st.markdown(f'<div class="mv-cta"><h3>Want this for your own portfolio?</h3><span style="color:#c8d3df">{text}</span><br>'
                f'<a class="b" href="{CONTACT}" target="_blank" rel="noopener">Talk to Munvest</a></div>', unsafe_allow_html=True)


def intro_page(tool="conjoint"):
    nm = TOOLS[tool]["name"]
    _header(f"Portfolio Intelligence - {nm} - Start here")
    if tool == "conjoint":
        st.markdown('<div class="mv-hero"><h2>What do your customers really value &ndash; and what would they pay for it?</h2>'
                    '<p>Conjoint analysis lets customers choose between realistic product variants. From a short survey it reveals which features drive '
                    'decisions, what upgrades are worth, and how a new or changed product would perform against alternatives.</p></div>', unsafe_allow_html=True)
        st.markdown("### How a conjoint study works")
        _step(1, "Design", "Your product features and their levels (for example processor: entry / mainstream / performance) are turned into a questionnaire.")
        _step(2, "Survey", "Each respondent answers background questions, screens out no-gos, makes eight A-vs-B choices, rates purchase likelihood and states willingness to pay (about 8&ndash;10 minutes).")
        _step(3, "Estimate", "A statistical model (multinomial logit and hierarchical Bayes) converts the choices into attribute importance and part-worth utilities per respondent.")
        _step(4, "Decide", "Use the market simulator, willingness to pay and segments to configure products, set prices and decide where to invest.")
        st.markdown('<div class="mv-note"><b>Demo data:</b> all results in this tool are dummy results from 50 simulated respondents. They illustrate the outputs &ndash; they are not market findings.</div>', unsafe_allow_html=True)
        st.markdown("### Agenda of this tool")
        agenda([("Start here", "Method, process and glossary", False),
                ("Portfolio Overview", "Summary of the study: respondents, top drivers, effect on the portfolio", False),
                ("Conjoint Results", "Importance, part-worths, willingness to pay, market simulator, purchase likelihood, segments", True),
                ("Your Conjoint Analysis with Munvest", "What a project looks like and how to start", False)])
        gl = """
- **Attribute importance**: how strongly a feature (e.g. price, battery) influences customer choice, in percent.
- **Part-worth utility**: the appeal of one specific level of a feature (e.g. 16 GB RAM) relative to the others.
- **Willingness to pay (WTP)**: the extra amount customers would pay for an upgrade.
- **Market simulator**: predicts the share of customers choosing each product in a market you define.
- **Hierarchical Bayes (HB)**: estimates preferences for every respondent individually, even from few choices.
- **Segments**: groups of respondents with similar preferences."""
    else:
        st.markdown('<div class="mv-hero"><h2>Which of your products compete with each other &ndash; and where is the market empty?</h2>'
                    '<p>Distance analysis measures how similar your products are across all their features. Near-identical products cannibalise each other, '
                    'large gaps are white space. Every chart comes with a short explanation.</p></div>', unsafe_allow_html=True)
        st.markdown("### How a distance analysis works")
        _step(1, "Collect", "Your products and their features (price, performance, size, brand, &hellip;) in one table.")
        _step(2, "Standardise", "Features are put on a common scale and weighted by importance &ndash; technically uniform, or by customer preference from a conjoint study.")
        _step(3, "Measure", "The distance between every pair of products is calculated; the closest products are each product&rsquo;s nearest neighbours.")
        _step(4, "Decide", "Read the traffic-light assessment, explore the product map and simulate removing products to see who takes over their customers.")
        st.markdown('<div class="mv-note"><b>Demo data:</b> the portfolios shown (smartphones, tractors) are public demonstration data for illustration &ndash; not your market.</div>', unsafe_allow_html=True)
        st.markdown("### Agenda of this tool")
        agenda([("Start here", "Method, process and glossary", False),
                ("Portfolio Overview", "Health of every portfolio at a glance", False),
                ("Distance Analysis", "Assessment per product, charts, product maps, removal simulation", True),
                ("Your Distance Analysis with Munvest", "What a project looks like and how to start", False)])
        gl = """
- **Distance**: how different two products are across all (standardised) features. 0 = identical; larger = more different.
- **Nearest neighbour**: the product closest to a given one &ndash; its most direct substitute.
- **Cannibalisation**: two of your own products are so similar that they take sales from each other.
- **White space**: a gap in the portfolio where no product serves a customer need.
- **Product map (PCA)**: a 2D/3D picture that keeps similar products together.
- **Customer-weighted view**: features that customers value more count more in the distance."""
    with st.expander("Glossary &ndash; key terms in plain language"):
        st.markdown(gl)
    _cta("A Munvest study is tailored to your products and customers. We design, run and interpret it with you.")
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


def overview_page(tool="distance"):
    if tool == "conjoint":
        return _conjoint_overview()
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
    _conjoint_block()
    st.markdown("### Where to go next")
    st.markdown("Open **Distance Analysis** in the menu, pick one of the products above and see its neighbours, assessment and product map.")
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


def _conjoint_overview():
    _header("Portfolio Overview")
    st.title("Study overview")
    st.caption("The demo study at a glance: who answered, what drives choices and what it means for the portfolio.")
    n = len(glob.glob("outputs/survey_responses_computers/*.csv"))
    imp = "outputs/conjoint_demo/importance.csv"
    k = st.columns(4)
    _kpi(k[0], n or "50", "Simulated respondents")
    _kpi(k[1], "8", "Choice tasks per respondent")
    _kpi(k[2], "6", "Upgrades for willingness to pay")
    _kpi(k[3], "MNL + HB", "Estimation methods")
    st.markdown("### What the study delivers")
    c = st.columns(3)
    _card(c[0], "Customer priorities", "Which features decide a purchase &ndash; ranked in percent, from price to performance.")
    _card(c[1], "Value of upgrades", "What a better processor, more memory or longer battery life is worth to customers, in money.")
    _card(c[2], "Market response", "How a product configuration performs against alternatives and in which customer segments.")
    _conjoint_block()
    st.markdown("### Where to go next")
    st.markdown("Open **Conjoint Results** in the menu for the full analysis, including the interactive market simulator. "
                "The portfolio view with customer-weighted distances is available in the [Distance Analysis tool](https://munvest-distance.streamlit.app).")
    import munvest_theme as mv; mv.footer()


def guide_page(tool="conjoint"):
    nm = TOOLS[tool]["name"]
    _header(f"Your {nm} with Munvest")
    st.title(f"Your {nm} with Munvest")
    st.caption("A rough outline of how a study works and what we need from you. The detailed set-up is where our experience matters.")
    if tool == "conjoint":
        st.markdown("### What you get")
        c = st.columns(3)
        _card(c[0], "Tailored survey", "A questionnaire built around <i>your</i> products, features and customers &ndash; in your language and tone.")
        _card(c[1], "Reliable results", "Importance, part-worths, willingness to pay, market simulator and segments, delivered as a dashboard like this one.")
        _card(c[2], "Decisions, not charts", "A workshop in which we turn the results into pricing, portfolio and positioning decisions.")
        st.markdown("### Rough outline of a project")
        _step(1, "Scope", "We clarify the decision to support, the products and the customer group. You provide a product and feature list.")
        _step(2, "Design", "We select the features and levels that matter, define the price range and build the questionnaire.")
        _step(3, "Field", "We test the survey, recruit or invite respondents and monitor data quality.")
        _step(4, "Analyse", "We estimate preferences, check model quality and build your dashboard.")
        _step(5, "Decide", "We present the results and develop recommendations with your team.")
        st.markdown("### What we need from you")
        st.markdown("- The decision you want to make (new product, pricing, portfolio clean-up)\n- Your products and their key features\n- Access to customers or a description of the target group")
    else:
        st.markdown("### What you get")
        c = st.columns(3)
        _card(c[0], "Portfolio X-ray", "A clear picture of which products overlap, which stand alone and where the market is empty.")
        _card(c[1], "Customer-weighted view", "Optionally combined with a conjoint study, so similarity reflects what customers value.")
        _card(c[2], "Decision support", "Removal and what-if simulations that show the effect of portfolio changes before you make them.")
        st.markdown("### Rough outline of a project")
        _step(1, "Scope", "We define the portfolio and the question: clean-up, new product, pricing corridor.")
        _step(2, "Data", "We build the product data set from your sources and public data, and agree which features count.")
        _step(3, "Analyse", "We compute distances, assess every product and map the portfolio.")
        _step(4, "Decide", "We discuss the findings and simulate portfolio changes with your team.")
        st.markdown("### What we need from you")
        st.markdown("- The product list with key features (an export is enough)\n- The questions you want answered\n- Optionally, results of a customer survey")
    _cta("Tell us about your portfolio and your decision &ndash; we will propose a study design and scope.")
    st.caption("Munvest combines consulting experience with analytics tools such as the ones shown here.")
    import munvest_theme as mv; mv.footer()


def _dl(label, *paths):
    path = next((x for x in paths if os.path.exists(x)), None)
    if path:
        with open(path, "rb") as f:
            st.download_button(label, f.read(), file_name=os.path.basename(path), key="dl_" + path)


def route(name, file):
    """Turn a plain app.py into the multipage Distance tool (returns True if the router ran)."""
    if name != "__main__":
        return False
    return run_distance_nav(file)


def run_distance_nav(file):
    import runpy
    def intro(): intro_page("distance")
    def overview(): overview_page("distance")
    def distance(): runpy.run_path(file, run_name="__distance__")
    def guide(): guide_page("distance")
    pg = st.navigation([
        st.Page(intro, title="Start here", url_path="start", default=True),
        st.Page(overview, title="Portfolio Overview", url_path="overview"),
        st.Page(distance, title="Distance Analysis", url_path="distance"),
        st.Page(guide, title="Your Distance Analysis with Munvest", url_path="study"),
    ])
    pg.run()
    return True
