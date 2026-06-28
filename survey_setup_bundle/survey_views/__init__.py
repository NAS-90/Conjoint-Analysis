"""Streamlit view code for the standalone conjoint survey app (``survey.py``).

Kept separate from :mod:`conjoint` (which stays dependency-light: ``pandas`` +
the standard library and must not import Streamlit) and from the analysis
dashboard (``app.py`` / :mod:`dashboard`). Every module here renders one survey
route referenced by the ``survey.py`` ``st.navigation`` router.
"""
