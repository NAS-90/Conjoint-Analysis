"""Munvest Distance Analysis - Streamlit Cloud entry point."""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import streamlit as st
import munvest_theme as mv
import munvest_pages as mp
import munvest_boot as boot

mv.install("Munvest Distance Analysis")


@st.cache_resource(show_spinner=False)
def _prepare():
    boot.ensure(responses=False)
    return True


with st.spinner("First start: preparing demo data (about 1 minute)..."):
    _prepare()

mp.run_distance_nav(os.path.join(ROOT, "app.py"))
