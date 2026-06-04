"""Unit tests for :mod:`survey_views.theme` helpers.

The important guarantee is :func:`safe_md`: respondent-facing price labels such
as "Mid-range ($300 – $700)" must render literally and never be parsed as
inline LaTeX math (a pair of ``$`` toggles math mode in Streamlit Markdown).
"""

from __future__ import annotations

import pytest

from survey_views.theme import safe_md


@pytest.mark.unit
def test_safe_md_escapes_dollar_signs() -> None:
    out = safe_md("Mid-range ($300 – $700)")
    # Every dollar sign is escaped → no unescaped $...$ pair survives.
    assert "\\$300" in out
    assert "\\$700" in out
    assert "$" not in out.replace("\\$", "")


@pytest.mark.unit
def test_safe_md_is_idempotent() -> None:
    once = safe_md("Budget (< $300)")
    twice = safe_md(once)
    assert once == twice


@pytest.mark.unit
def test_safe_md_normalises_pre_escaped_input() -> None:
    # A label that already escaped its dollar should not gain a stray backslash.
    assert safe_md(r"Budget (< \$300)") == safe_md("Budget (< $300)")


@pytest.mark.unit
def test_safe_md_handles_none_and_non_strings() -> None:
    assert safe_md(None) == ""
    assert safe_md(12) == "12"
