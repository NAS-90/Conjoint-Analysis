"""Tests for the table-driven Part A / Part C sections.

The loader (:mod:`survey_views.section_source`) reads a ``Survey_questions``
sheet directly from a per-product workbook at runtime, falling back fail-soft to
the built-in defaults when the workbook/sheet is absent or invalid.
"""

from __future__ import annotations

import pandas as pd

from survey_views import section_source as ss

_COLUMNS = ["section", "id", "prompt", "input_type", "options", "help"]


def _write_workbook(path, rows, sheet=ss.SHEET):
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(rows, columns=_COLUMNS).to_excel(writer, sheet_name=sheet, index=False)
    return path


def _sample_rows() -> list[dict]:
    return [
        {"section": "A", "id": "q1", "prompt": "P?", "input_type": "single",
         "options": "a; b; c", "help": "h"},
        {"section": "A", "id": "q2", "prompt": "M?", "input_type": "multi",
         "options": "x; y", "help": ""},
        {"section": "bands", "id": "z", "prompt": "Zero"},
        {"section": "bands", "id": "m", "prompt": "More"},
        {"section": "C", "id": "f1", "prompt": "Feat 1"},
        {"section": "", "id": "", "prompt": ""},  # blank spacer row → ignored
    ]


# ---------------------------------------------------------------------------
# Fallback to defaults
# ---------------------------------------------------------------------------
def test_loaders_fall_back_when_workbook_absent(tmp_path) -> None:
    missing = tmp_path / "nope.xlsx"
    assert ss.load_background_questions(missing) == ss.DEFAULT_PROFILE_QUESTIONS
    assert ss.load_wtp_features(missing) == ss.DEFAULT_WTP_FEATURES
    assert ss.load_amount_bands(missing) == ss.DEFAULT_AMOUNT_BANDS


def test_loader_falls_back_when_sheet_missing(tmp_path) -> None:
    path = tmp_path / "wb.xlsx"
    _write_workbook(path, _sample_rows(), sheet="SomethingElse")
    assert ss.load_background_questions(path) == ss.DEFAULT_PROFILE_QUESTIONS


def test_loader_is_fail_soft_on_too_few_options(tmp_path) -> None:
    path = tmp_path / "wb.xlsx"
    _write_workbook(path, [{"section": "A", "id": "q", "prompt": "P?", "options": "only"}])
    assert ss.load_background_questions(path) == ss.DEFAULT_PROFILE_QUESTIONS


def test_loader_is_fail_soft_on_duplicate_ids(tmp_path) -> None:
    path = tmp_path / "wb.xlsx"
    _write_workbook(
        path,
        [
            {"section": "C", "id": "f1", "prompt": "A"},
            {"section": "C", "id": "f1", "prompt": "B"},
        ],
    )
    assert ss.load_wtp_features(path) == ss.DEFAULT_WTP_FEATURES


def test_loader_falls_back_per_section(tmp_path) -> None:
    """An invalid Part A doesn't sink a valid Part C (each section is independent)."""
    path = tmp_path / "wb.xlsx"
    _write_workbook(
        path,
        [
            {"section": "A", "id": "bad", "prompt": "x?", "options": "one"},  # invalid
            {"section": "C", "id": "f1", "prompt": "Feature 1"},  # valid
        ],
    )
    assert ss.load_background_questions(path) == ss.DEFAULT_PROFILE_QUESTIONS
    assert ss.load_wtp_features(path) == (ss.WtpFeature("f1", "Feature 1"),)


# ---------------------------------------------------------------------------
# Reading a custom workbook
# ---------------------------------------------------------------------------
def test_loaders_read_a_custom_workbook(tmp_path) -> None:
    path = tmp_path / "survey_questions.xlsx"
    _write_workbook(path, _sample_rows())

    assert ss.load_background_questions(path) == (
        ss.ProfileQuestion("q1", "P?", ("a", "b", "c"), False, "h"),
        ss.ProfileQuestion("q2", "M?", ("x", "y"), True, ""),
    )
    assert ss.load_wtp_features(path) == (ss.WtpFeature("f1", "Feat 1"),)
    assert ss.load_amount_bands(path) == (("z", "Zero"), ("m", "More"))


def test_env_var_selects_the_workbook(tmp_path, monkeypatch) -> None:
    path = tmp_path / "from_env.xlsx"
    _write_workbook(path, _sample_rows())
    monkeypatch.setenv("SURVEY_WORKBOOK", str(path))
    # No explicit arg → resolver picks up the env var.
    assert ss.load_wtp_features() == (ss.WtpFeature("f1", "Feat 1"),)


# ---------------------------------------------------------------------------
# The committed smartphone workbook is well-formed
# ---------------------------------------------------------------------------
def test_committed_default_workbook_loads() -> None:
    """The bundled survey_questions.xlsx parses into non-empty, unique sections."""
    background = ss.load_background_questions()
    features = ss.load_wtp_features()
    assert background and len({q.identifier for q in background}) == len(background)
    assert features and len({f.identifier for f in features}) == len(features)
