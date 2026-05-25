from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def sample_workbook(tmp_path: Path) -> Path:
    path = tmp_path / "sample_products.xlsx"

    edited = pd.DataFrame(
        {
            "product_id": ["P1", "P2", "P3"],
            "engine": ["basic", "premium", "premium"],
            "transmission_type": ["manual", "powershift", "cvt"],
            "price": [100.0, 130.0, 150.0],
            "has_cabin": ["yes", "no", "yes"],
        }
    )
    feature_data = pd.DataFrame(
        [
            {
                "feature_name": "product_id",
                "description": "Identifier",
                "data_types": "nominal",
                "included_in_analysis": "no",
                "normalization_method": "none",
                "ideal_direction": "neutral",
                "weight_importance": "none",
                "conjoint_role": "identifier",
                "conjoint_levels": "",
                "conjoint_level_codes": "",
                "conjoint_question_type": "",
                "conjoint_section": "",
            },
            {
                "feature_name": "engine",
                "description": "Engine package",
                "data_types": "nominal",
                "included_in_analysis": "yes",
                "normalization_method": "none",
                "ideal_direction": "neutral",
                "weight_importance": "medium",
                "conjoint_role": "attribute",
                "conjoint_levels": "basic; premium",
                "conjoint_level_codes": "basic; premium",
                "conjoint_question_type": "rating",
                "conjoint_section": "B1_rating",
            },
            {
                "feature_name": "transmission_type",
                "description": "Transmission",
                "data_types": "nominal",
                "included_in_analysis": "yes",
                "normalization_method": "none",
                "ideal_direction": "neutral",
                "weight_importance": "high",
                "conjoint_role": "attribute",
                "conjoint_levels": "manual; powershift; cvt",
                "conjoint_level_codes": "manual; powershift; cvt",
                "conjoint_question_type": "rating",
                "conjoint_section": "B1_rating",
            },
            {
                "feature_name": "price",
                "description": "Price",
                "data_types": "metric",
                "included_in_analysis": "yes",
                "normalization_method": "z-score",
                "ideal_direction": "lower",
                "weight_importance": "low",
                "conjoint_role": "skip",
                "conjoint_levels": "",
                "conjoint_level_codes": "",
                "conjoint_question_type": "",
                "conjoint_section": "",
            },
            {
                "feature_name": "has_cabin",
                "description": "Cabin available",
                "data_types": "binary",
                "included_in_analysis": "yes",
                "normalization_method": "none",
                "ideal_direction": "neutral",
                "weight_importance": "medium",
                "conjoint_role": "attribute",
                "conjoint_levels": "no; yes",
                "conjoint_level_codes": "no; yes",
                "conjoint_question_type": "rating",
                "conjoint_section": "B1_rating",
            },
        ]
    )

    with pd.ExcelWriter(path) as writer:
        edited.to_excel(writer, sheet_name="Edited", index=False)
        feature_data.to_excel(writer, sheet_name="Feature_data", index=False)

    return path


@pytest.fixture
def n381_fixture_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "n381"
