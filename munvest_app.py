"""Munvest Conjoint Analysis - Streamlit Cloud entry point."""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import streamlit as st
import munvest_theme as mv
import munvest_pages as mp
import munvest_boot as boot

mv.install("Munvest Conjoint Analysis")


@st.cache_resource(show_spinner=False)
def _prepare():
    boot.ensure(responses=True)
    return True


def results_page():
    mv.apply(); mp._css()
    mv.header("Portfolio Intelligence - Conjoint Analysis - Results")
    mp.agenda([("Overview & convergence", "Sample size and model quality", False),
               ("Attribute importance", "What drives customer choice", False),
               ("Part-worth utilities", "Appeal of every feature level", False),
               ("Willingness-to-pay", "Stated and derived value of upgrades; pick a feature to see its distribution", True),
               ("Market simulator", "Configure products and see predicted market shares", True),
               ("Purchase likelihood", "How likely customers are to buy the configured product", False),
               ("Respondent segments", "Groups with similar preferences", False)])
    st.markdown('<div class="mv-note"><b>Demo data:</b> dummy results from 50 simulated respondents, for illustration only.</div>', unsafe_allow_html=True)
    from dashboard.results_dashboard import render_results_dashboard
    render_results_dashboard()
    mv.footer()


with st.spinner("First start: preparing demo data (1-2 minutes)..."):
    _prepare()

pg = st.navigation([
    st.Page(lambda: mp.intro_page("conjoint"), title="Start here", url_path="start", default=True),
    st.Page(lambda: mp.overview_page("conjoint"), title="Portfolio Overview", url_path="overview"),
    st.Page(results_page, title="Conjoint Results", url_path="results"),
    st.Page(lambda: mp.guide_page("conjoint"), title="Your study with Munvest", url_path="study"),
])
pg.run()
