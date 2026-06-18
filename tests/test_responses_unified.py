"""Tests for the unified survey response schema (Part A/B/C assemble helpers)."""

from __future__ import annotations

from conjoint.acbc import responses as r
from conjoint.acbc.design import Profile

ATTRIBUTE_LEVELS = {
    "os": ("android", "ios"),
    "storage": ("64gb", "128gb", "256gb"),
}
ATTR_COLS = ["os=level", "storage=level"]


def _base_cols(frame) -> None:
    """Every assembled frame carries the fixed columns + one col per attribute."""
    assert list(frame.columns) == list(r.FIXED_COLUMNS) + ATTR_COLS


def test_fixed_columns_include_item_and_response_value() -> None:
    assert r.ITEM_COL in r.FIXED_COLUMNS
    assert r.RESPONSE_VALUE_COL in r.FIXED_COLUMNS
    # ...appended after the original choice columns (back-compat for estimation).
    assert r.FIXED_COLUMNS[:5] == (
        r.RESPONDENT_COL,
        r.STAGE_COL,
        r.TASK_ID_COL,
        r.ALTERNATIVE_INDEX_COL,
        r.CHOSEN_COL,
    )


def test_assemble_background_responses() -> None:
    records = [r.BackgroundResponse("r1", 1, "budget", "Under $300")]
    frame = r.assemble_background_responses(records, ATTRIBUTE_LEVELS)
    _base_cols(frame)
    row = frame.iloc[0]
    assert row["stage"] == r.STAGE_BACKGROUND
    assert row["item"] == "budget"
    assert row["response_value"] == "Under $300"
    assert row["chosen"] == ""
    assert row["os=level"] == "" and row["storage=level"] == ""


def test_assemble_rating_responses() -> None:
    records = [r.RatingResponse("r1", 1, "os", "ios", 4)]
    frame = r.assemble_rating_responses(records, ATTRIBUTE_LEVELS)
    _base_cols(frame)
    row = frame.iloc[0]
    assert row["stage"] == r.STAGE_RATING
    assert row["item"] == "os"
    assert row["response_value"] == 4
    assert row["os=level"] == "ios"
    assert row["storage=level"] == ""


def test_assemble_musthave_responses() -> None:
    records = [
        r.ConstraintResponse("r1", 1, "os", "ios", "must_have"),
        r.ConstraintResponse("r1", 2, "storage", "64gb", "unacceptable"),
    ]
    frame = r.assemble_musthave_responses(records, ATTRIBUTE_LEVELS)
    _base_cols(frame)
    assert list(frame["stage"]) == [r.STAGE_MUSTHAVE, r.STAGE_MUSTHAVE]
    assert list(frame["response_value"]) == ["must_have", "unacceptable"]
    assert list(frame["os=level"]) == ["ios", ""]
    assert list(frame["storage=level"]) == ["", "64gb"]


def test_assemble_calibration_responses() -> None:
    profile = Profile((("os", "ios"), ("storage", "128gb")))
    frame = r.assemble_calibration_responses(
        [r.CalibrationResponse("r1", 1, profile, 3)], ATTRIBUTE_LEVELS
    )
    _base_cols(frame)
    row = frame.iloc[0]
    assert row["stage"] == r.STAGE_CALIBRATION
    assert row["response_value"] == 3
    assert row["chosen"] == ""
    assert row["os=level"] == "ios" and row["storage=level"] == "128gb"


def test_assemble_wtp_responses() -> None:
    frame = r.assemble_wtp_responses(
        [r.WtpResponse("r1", 1, "camera", "up_to_100")], ATTRIBUTE_LEVELS
    )
    _base_cols(frame)
    row = frame.iloc[0]
    assert row["stage"] == r.STAGE_WTP
    assert row["item"] == "camera"
    assert row["response_value"] == "up_to_100"


def test_concat_and_validate_accepts_all_new_stages() -> None:
    profile = Profile((("os", "ios"), ("storage", "128gb")))
    frames = [
        r.assemble_background_responses(
            [r.BackgroundResponse("r1", 1, "budget", "Under $300")], ATTRIBUTE_LEVELS
        ),
        r.assemble_rating_responses(
            [r.RatingResponse("r1", 1, "os", "ios", 5)], ATTRIBUTE_LEVELS
        ),
        r.assemble_musthave_responses(
            [r.ConstraintResponse("r1", 1, "os", "ios", "must_have")], ATTRIBUTE_LEVELS
        ),
        r.assemble_calibration_responses(
            [r.CalibrationResponse("r1", 1, profile, 4)], ATTRIBUTE_LEVELS
        ),
        r.assemble_wtp_responses(
            [r.WtpResponse("r1", 1, "camera", "none")], ATTRIBUTE_LEVELS
        ),
    ]
    merged = r.concat_responses(*frames)
    assert len(merged) == 5
    assert set(merged["stage"]) == {
        r.STAGE_BACKGROUND,
        r.STAGE_RATING,
        r.STAGE_MUSTHAVE,
        r.STAGE_CALIBRATION,
        r.STAGE_WTP,
    }
    # The blank-chosen value-style rows must pass validation.
    assert r.validate_acbc_responses(merged, ATTRIBUTE_LEVELS) == []
