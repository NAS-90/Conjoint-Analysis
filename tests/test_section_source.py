"""Tests for the table-driven Part A / Part C sections.

Covers the runtime loader (:mod:`survey_views.section_source`) and the
``Survey_questions`` sheet → ``survey_questions.json`` generator
(:mod:`conjoint.generate_survey_questions`).
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from conjoint import generate_survey_questions as gen
from survey_views import section_source as ss


# ---------------------------------------------------------------------------
# Loader — fail-soft fallback to defaults
# ---------------------------------------------------------------------------
def test_loaders_fall_back_to_defaults_when_file_absent(tmp_path) -> None:
    missing = tmp_path / "nope.json"
    assert ss.load_background_questions(missing) == ss.DEFAULT_PROFILE_QUESTIONS
    assert ss.load_wtp_features(missing) == ss.DEFAULT_WTP_FEATURES
    assert ss.load_amount_bands(missing) == ss.DEFAULT_AMOUNT_BANDS


def test_loaders_read_a_custom_file(tmp_path) -> None:
    doc = {
        "version": "0.1",
        "background": [
            {"id": "q1", "prompt": "Pick one?", "input_type": "single",
             "options": ["a", "b"]},
            {"id": "q2", "prompt": "Pick many?", "input_type": "multi",
             "options": ["x", "y", "z"], "help": "all that apply"},
        ],
        "wtp": {
            "amount_bands": [["z", "Zero"], ["m", "More"]],
            "features": [{"id": "f1", "label": "Feature 1"}],
        },
    }
    path = tmp_path / "survey_questions.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    assert ss.load_background_questions(path) == (
        ss.ProfileQuestion("q1", "Pick one?", ("a", "b"), False, ""),
        ss.ProfileQuestion("q2", "Pick many?", ("x", "y", "z"), True, "all that apply"),
    )
    assert ss.load_wtp_features(path) == (ss.WtpFeature("f1", "Feature 1"),)
    assert ss.load_amount_bands(path) == (("z", "Zero"), ("m", "More"))


def test_loader_is_fail_soft_on_malformed_json(tmp_path) -> None:
    path = tmp_path / "survey_questions.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    assert ss.load_background_questions(path) == ss.DEFAULT_PROFILE_QUESTIONS


def test_loader_falls_back_per_section_on_invalid_content(tmp_path) -> None:
    # 'background' invalid (one option) → background defaults; wtp still honoured.
    doc = {
        "background": [{"id": "q1", "prompt": "x?", "options": ["only-one"]}],
        "wtp": {"features": [{"id": "f1", "label": "F1"}]},
    }
    path = tmp_path / "survey_questions.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert ss.load_background_questions(path) == ss.DEFAULT_PROFILE_QUESTIONS
    assert ss.load_wtp_features(path) == (ss.WtpFeature("f1", "F1"),)


# ---------------------------------------------------------------------------
# Generator — Survey_questions DataFrame → document
# ---------------------------------------------------------------------------
def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"section": "A", "id": "q1", "prompt": "P?", "input_type": "single",
             "options": "a; b; c", "help": "h"},
            {"section": "A", "id": "q2", "prompt": "M?", "input_type": "multi",
             "options": "x; y", "help": ""},
            {"section": "bands", "id": "z", "prompt": "Zero",
             "input_type": "", "options": "", "help": ""},
            {"section": "bands", "id": "m", "prompt": "More",
             "input_type": "", "options": "", "help": ""},
            {"section": "C", "id": "f1", "prompt": "Feat 1",
             "input_type": "", "options": "", "help": ""},
            {"section": "", "id": "", "prompt": "", "input_type": "",
             "options": "", "help": ""},  # blank spacer row → ignored
        ]
    )


def test_build_questions_from_dataframe() -> None:
    doc = gen.build_questions(_sample_df())
    assert doc["background"][0] == {
        "id": "q1", "prompt": "P?", "input_type": "single",
        "options": ["a", "b", "c"], "help": "h",
    }
    assert doc["background"][1]["input_type"] == "multi"
    assert "help" not in doc["background"][1]  # blank help omitted
    assert doc["wtp"]["amount_bands"] == [["z", "Zero"], ["m", "More"]]
    assert doc["wtp"]["features"] == [{"id": "f1", "label": "Feat 1"}]


def test_build_questions_rejects_too_few_options() -> None:
    df = pd.DataFrame([{"section": "A", "id": "q", "prompt": "P?", "options": "only"}])
    with pytest.raises(ValueError, match=">=2 options"):
        gen.build_questions(df)


def test_build_questions_rejects_duplicate_ids() -> None:
    df = pd.DataFrame(
        [
            {"section": "C", "id": "f1", "prompt": "A"},
            {"section": "C", "id": "f1", "prompt": "B"},
        ]
    )
    with pytest.raises(ValueError, match="duplicate"):
        gen.build_questions(df)


def test_build_questions_rejects_unknown_section() -> None:
    df = pd.DataFrame([{"section": "Z", "id": "x", "prompt": "P?"}])
    with pytest.raises(ValueError, match="unknown section"):
        gen.build_questions(df)


# ---------------------------------------------------------------------------
# End-to-end: Excel sheet → JSON → loader
# ---------------------------------------------------------------------------
def test_workbook_to_json_to_loader_roundtrip(tmp_path) -> None:
    workbook = tmp_path / "wb.xlsx"
    with pd.ExcelWriter(workbook) as writer:
        _sample_df().to_excel(writer, sheet_name="Survey_questions", index=False)

    document = gen.build_from_workbook(workbook)
    out = gen.write_questions(document, tmp_path / "survey_questions.json")

    assert ss.load_background_questions(out) == (
        ss.ProfileQuestion("q1", "P?", ("a", "b", "c"), False, "h"),
        ss.ProfileQuestion("q2", "M?", ("x", "y"), True, ""),
    )
    assert ss.load_wtp_features(out) == (ss.WtpFeature("f1", "Feat 1"),)
    assert ss.load_amount_bands(out) == (("z", "Zero"), ("m", "More"))


def test_defaults_roundtrip_through_generator(tmp_path) -> None:
    """The committed defaults survive a defaults→sheet→json→load round-trip."""
    rows = []
    for q in ss.DEFAULT_PROFILE_QUESTIONS:
        rows.append({"section": "A", "id": q.identifier, "prompt": q.prompt,
                     "input_type": "multi" if q.multi else "single",
                     "options": "; ".join(q.options), "help": q.help})
    for code, label in ss.DEFAULT_AMOUNT_BANDS:
        rows.append({"section": "bands", "id": code, "prompt": label,
                     "input_type": "", "options": "", "help": ""})
    for feature in ss.DEFAULT_WTP_FEATURES:
        rows.append({"section": "C", "id": feature.identifier, "prompt": feature.label,
                     "input_type": "", "options": "", "help": ""})

    document = gen.build_questions(pd.DataFrame(rows))
    out = gen.write_questions(document, tmp_path / "survey_questions.json")

    assert ss.load_background_questions(out) == ss.DEFAULT_PROFILE_QUESTIONS
    assert ss.load_wtp_features(out) == ss.DEFAULT_WTP_FEATURES
    assert ss.load_amount_bands(out) == ss.DEFAULT_AMOUNT_BANDS
