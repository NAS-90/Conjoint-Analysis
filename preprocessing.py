from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_EXCEL = "Database_Distance Analysis.xlsx"
DATA_SHEET = "Edited"
META_SHEET = "Feature_data"
OUTPUT_CSV = "preprocessed_output.csv"

YES_VALUES = {"yes", "y", "true", "1", "included", "include"}
NO_VALUES = {"no", "n", "false", "0", "excluded", "exclude", "nan", ""}

TYPE_ALIASES = {
    "numeric": "metric",
    "number": "metric",
    "continuous": "metric",
    "categorical": "nominal",
    "category": "nominal",
    "normal": "nominal",
    "boolean": "binary",
    "bool": "binary",
    "string": "text",
}

NORM_ALIASES = {
    "": "none",
    "nan": "none",
    "normalization_meth": "none",
    "ordinal mapping": "ordinal-mapping",
    "ordinal_mapping": "ordinal-mapping",
    "ordinal-map": "ordinal-mapping",
    "standard": "z-score",
    "standardize": "z-score",
    "standardized": "z-score",
    "zscore": "z-score",
    "z_score": "z-score",
    "minmax": "min-max",
    "min_max": "min-max",
}

IDEAL_ALIASES = {
    "": "neutral",
    "nan": "neutral",
    "none": "neutral",
    "neutral": "neutral",
    "higher is better": "higher",
    "higher": "higher",
    "high": "higher",
    "lower is better": "lower",
    "lower": "lower",
    "low": "lower",
}

COLUMN_ALIASES = {
    "feature": "feature_name",
    "features": "feature_name",
    "name": "feature_name",
    "type": "data_types",
    "data_type": "data_types",
    "datatype": "data_types",
    "include": "included_in_analysis",
    "included": "included_in_analysis",
    "normalisation_method": "normalization_method",
    "normalization": "normalization_method",
    "ideal": "ideal_direction",
    "direction": "ideal_direction",
}

REQUIRED_META_COLUMNS = {"feature_name", "data_types", "included_in_analysis"}
PREPROCESS_META_COLUMNS = [
    "feature_name",
    "data_types",
    "included_in_analysis",
    "normalization_method",
    "ideal_direction",
]


@dataclass
class FeatureResult:
    feature_name: str
    data_type: str
    normalization_method: str
    ideal_direction: str
    output_columns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PreprocessResult:
    excel_path: Path
    output_path: Path
    data_rows: int
    raw_feature_count: int
    metadata_rows: int
    included_feature_count: int
    output_feature_count: int
    warnings: list[str]
    feature_results: list[FeatureResult]


class PreprocessError(ValueError):
    pass


def normalize_label(value: object) -> str:
    label = str(value).strip().lower()
    label = re.sub(r"\s+", "_", label)
    label = re.sub(r"[^a-z0-9_]+", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return COLUMN_ALIASES.get(label, label)


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def canonical_type(value: object) -> str:
    raw = clean_text(value).lower()
    return TYPE_ALIASES.get(raw, raw)


def canonical_norm(value: object) -> str:
    raw = clean_text(value).lower()
    return NORM_ALIASES.get(raw, raw)


def canonical_ideal(value: object) -> str:
    raw = clean_text(value).lower()
    return IDEAL_ALIASES.get(raw, raw)


def canonical_included(value: object) -> str:
    raw = clean_text(value).lower()
    if raw in YES_VALUES:
        return "yes"
    if raw in NO_VALUES:
        return "no"
    return raw


def require_sheets(excel_path: Path, data_sheet: str, meta_sheet: str) -> None:
    if not excel_path.exists():
        raise FileNotFoundError(f"Missing workbook: {excel_path}")

    sheets = set(pd.ExcelFile(excel_path).sheet_names)
    missing = [sheet for sheet in [data_sheet, meta_sheet] if sheet not in sheets]
    if missing:
        raise PreprocessError(
            f"{excel_path} is missing required sheet(s): {', '.join(missing)}"
        )


def normalize_metadata(meta: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    meta = meta.copy()
    meta.columns = [normalize_label(c) for c in meta.columns]
    meta = meta.dropna(how="all")

    missing = sorted(REQUIRED_META_COLUMNS - set(meta.columns))
    if missing:
        raise PreprocessError(
            "Feature_data is missing required column(s): " + ", ".join(missing)
        )

    for col in ["normalization_method", "ideal_direction"]:
        if col not in meta.columns:
            meta[col] = "none" if col == "normalization_method" else "neutral"
            warnings.append(f"Feature_data missing '{col}', defaulted to '{meta[col].iloc[0]}'.")

    for col in PREPROCESS_META_COLUMNS:
        meta[col] = meta[col].map(clean_text)

    meta["feature_name"] = meta["feature_name"].map(str.strip)
    meta = meta[meta["feature_name"] != ""].copy()

    duplicated_header_mask = meta.apply(
        lambda row: normalize_label(row.get("feature_name", "")) == "feature_name"
        or normalize_label(row.get("included_in_analysis", "")) == "included_in_analysis"
        or normalize_label(row.get("data_types", "")) == "data_types",
        axis=1,
    )
    if duplicated_header_mask.any():
        warnings.append(
            f"Dropped {int(duplicated_header_mask.sum())} duplicated header row(s) from Feature_data."
        )
        meta = meta[~duplicated_header_mask].copy()

    meta["data_types"] = meta["data_types"].map(canonical_type)
    meta["included_in_analysis"] = meta["included_in_analysis"].map(canonical_included)
    meta["normalization_method"] = meta["normalization_method"].map(canonical_norm)
    meta["ideal_direction"] = meta["ideal_direction"].map(canonical_ideal)

    duplicate_features = meta["feature_name"][meta["feature_name"].duplicated()].tolist()
    if duplicate_features:
        warnings.append(
            "Feature_data has duplicate feature rows; keeping first occurrence(s): "
            + ", ".join(sorted(set(duplicate_features)))
        )
        meta = meta.drop_duplicates(subset=["feature_name"], keep="first").copy()

    return meta.reset_index(drop=True)


def included_features(meta: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    unexpected = sorted(
        value
        for value in meta["included_in_analysis"].dropna().unique()
        if value not in {"yes", "no"}
    )
    if unexpected:
        warnings.append(
            "Unexpected included_in_analysis value(s) treated as 'no': "
            + ", ".join(unexpected)
        )

    included = meta[meta["included_in_analysis"] == "yes"].copy()
    if included.empty:
        raise PreprocessError("Feature_data marks no features as included_in_analysis=yes.")
    return included


def to_binary(series: pd.Series) -> pd.Series:
    truthy = {
        "yes",
        "y",
        "true",
        "1",
        "available",
        "supported",
        "memory card supported",
    }
    falsy = {
        "no",
        "n",
        "false",
        "0",
        "not available",
        "unsupported",
        "not supported",
        "memory card not supported",
        "nan",
        "",
    }

    def convert(value: object) -> int:
        if pd.isna(value):
            return 0
        if isinstance(value, (bool, np.bool_)):
            return int(value)
        text = str(value).strip().lower()
        text = re.sub(r"^[\u2022\u00b7\*\-\+]+\s*", "", text)
        if text in truthy or text.startswith("true"):
            return 1
        if text in falsy or text.startswith("false"):
            return 0
        return 0

    return series.map(convert).astype(int)


def numeric_tokens(value: object) -> list[str]:
    if pd.isna(value):
        return []
    text = str(value).replace(",", "")
    return re.findall(r"[-+]?\d+(?:\.\d+)?", text)


def universal_numeric_cleaner(value: object) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).replace(",", "")
    compact = re.sub(r"[^\d.\-+]", "", text)
    if compact in {"", ".", "-", "+", "-.", "+."}:
        return np.nan
    try:
        return float(compact)
    except ValueError:
        tokens = numeric_tokens(value)
        return float(tokens[0]) if tokens else np.nan


def parse_range(value: object) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).strip().replace("–", "-").replace("—", "-")
    match = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)\s*-\s*([-+]?\d+(?:\.\d+)?)\s*$", text)
    if match:
        return (float(match.group(1)) + float(match.group(2))) / 2.0
    tokens = numeric_tokens(value)
    return float(tokens[0]) if tokens else np.nan


def parse_multi_numbers(value: object) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).lower().replace("×", "x")
    if "x" in text:
        tokens = numeric_tokens(text)
        if len(tokens) >= 2:
            return float(tokens[-2]) * float(tokens[-1])
    return universal_numeric_cleaner(value)


def parse_ordinal(value: object) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).strip().lower().replace("×", "x")
    if re.search(r"\d\s*[-–—]\s*\d", text):
        return parse_range(value)
    if "x" in text:
        return parse_multi_numbers(value)
    return universal_numeric_cleaner(value)


def scale_values(values: pd.Series, method: str, ideal_direction: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)

    if numeric.notna().sum() == 0:
        return pd.Series(np.zeros(len(numeric)), index=numeric.index, dtype=float)

    if method == "min-max":
        min_val = numeric.min(skipna=True)
        max_val = numeric.max(skipna=True)
        span = max_val - min_val
        if pd.isna(span) or span == 0:
            scaled = pd.Series(np.zeros(len(numeric)), index=numeric.index, dtype=float)
        else:
            scaled = (numeric - min_val) / span
        if ideal_direction == "lower":
            scaled = 1 - scaled
        return scaled

    if method == "z-score":
        mean = numeric.mean(skipna=True)
        std = numeric.std(skipna=True, ddof=0)
        if pd.isna(std) or std == 0:
            return pd.Series(np.zeros(len(numeric)), index=numeric.index, dtype=float)
        return (numeric - mean) / std

    return numeric


def fill_numeric_missing(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            out[col] = pd.to_numeric(out[col], errors="coerce")
        if out[col].isna().all():
            out[col] = 0
        elif out[col].isna().any():
            out[col] = out[col].fillna(out[col].mean())
    return out


def validate_feature_rules(row: pd.Series, warnings: list[str]) -> tuple[str, str, str] | None:
    feature = row["feature_name"]
    data_type = row["data_types"]
    norm = row["normalization_method"]
    ideal = row["ideal_direction"]

    if data_type not in {"metric", "ordinal", "binary", "nominal", "text"}:
        warnings.append(f"{feature}: unsupported data_types='{data_type}', skipped.")
        return None

    if norm not in {"z-score", "min-max", "ordinal-mapping", "none"}:
        warnings.append(f"{feature}: unsupported normalization_method='{norm}', using 'none'.")
        norm = "none"

    if ideal not in {"higher", "lower", "neutral"}:
        warnings.append(f"{feature}: unsupported ideal_direction='{ideal}', using 'neutral'.")
        ideal = "neutral"

    if data_type == "metric" and norm == "none":
        warnings.append(f"{feature}: metric feature has normalization_method=none; using raw numeric values.")

    if data_type == "ordinal" and norm == "none":
        warnings.append(f"{feature}: ordinal feature has normalization_method=none; using parsed ordinal values.")

    return data_type, norm, ideal


def transform_feature(row: pd.Series, df_raw: pd.DataFrame, warnings: list[str]) -> tuple[pd.DataFrame, FeatureResult | None]:
    feature = row["feature_name"]
    if feature not in df_raw.columns:
        warnings.append(f"{feature}: listed in Feature_data but missing from Edited; skipped.")
        return pd.DataFrame(index=df_raw.index), None

    cleaned_rules = validate_feature_rules(row, warnings)
    if cleaned_rules is None:
        return pd.DataFrame(index=df_raw.index), None
    data_type, norm, ideal = cleaned_rules

    result = FeatureResult(
        feature_name=feature,
        data_type=data_type,
        normalization_method=norm,
        ideal_direction=ideal,
    )

    series = df_raw[feature]
    if data_type == "metric":
        parsed = series.map(universal_numeric_cleaner)
        transformed = scale_values(parsed, norm, ideal)
        out = pd.DataFrame({feature: transformed}, index=df_raw.index)
        result.output_columns = [feature]
        if parsed.isna().any():
            result.notes.append(f"{int(parsed.isna().sum())} value(s) parsed as missing and imputed.")
        return out, result

    if data_type == "ordinal":
        parsed = series.map(parse_ordinal)
        method = norm if norm in {"min-max", "z-score"} else "none"
        transformed = scale_values(parsed, method, ideal)
        out = pd.DataFrame({feature: transformed}, index=df_raw.index)
        result.output_columns = [feature]
        if parsed.isna().any():
            result.notes.append(f"{int(parsed.isna().sum())} value(s) parsed as missing and imputed.")
        return out, result

    if data_type == "binary":
        out = pd.DataFrame({feature: to_binary(series)}, index=df_raw.index)
        result.output_columns = [feature]
        return out, result

    dummies = pd.get_dummies(series, prefix=feature)
    dummies = dummies.reindex(sorted(dummies.columns), axis=1)
    result.output_columns = [str(col) for col in dummies.columns]
    if data_type == "text":
        result.notes.append("Included text feature encoded as one-hot categories.")
    return dummies, result


def preprocess_workbook(
    excel_path: Path,
    output_path: Path,
    data_sheet: str = DATA_SHEET,
    meta_sheet: str = META_SHEET,
    validation_report: Path | None = None,
) -> PreprocessResult:
    warnings: list[str] = []
    require_sheets(excel_path, data_sheet, meta_sheet)

    df_raw = pd.read_excel(excel_path, sheet_name=data_sheet)
    meta_raw = pd.read_excel(excel_path, sheet_name=meta_sheet)
    meta = normalize_metadata(meta_raw, warnings)
    meta_inc = included_features(meta, warnings)

    transformed_frames: list[pd.DataFrame] = []
    feature_results: list[FeatureResult] = []
    for _, row in meta_inc.iterrows():
        frame, result = transform_feature(row, df_raw, warnings)
        if result is not None and not frame.empty:
            transformed_frames.append(frame)
            feature_results.append(result)

    if not transformed_frames:
        raise PreprocessError("No usable features were produced from Feature_data.")

    processed = pd.concat(transformed_frames, axis=1)
    processed = fill_numeric_missing(processed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(output_path, index=False)

    result = PreprocessResult(
        excel_path=excel_path,
        output_path=output_path,
        data_rows=len(df_raw),
        raw_feature_count=len(df_raw.columns),
        metadata_rows=len(meta),
        included_feature_count=len(meta_inc),
        output_feature_count=processed.shape[1],
        warnings=warnings,
        feature_results=feature_results,
    )

    if validation_report is not None:
        write_validation_report(validation_report, result)

    return result


def write_validation_report(path: Path, result: PreprocessResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Universal Preprocessor Validation — {result.excel_path.name}",
        "",
        "## Summary",
        f"- Workbook: `{result.excel_path}`",
        f"- Output: `{result.output_path}`",
        f"- Input rows: {result.data_rows}",
        f"- Raw columns in `Edited`: {result.raw_feature_count}",
        f"- Metadata rows used: {result.metadata_rows}",
        f"- Included source features: {result.included_feature_count}",
        f"- Output numeric features: {result.output_feature_count}",
        "",
        "## Warnings",
    ]

    if result.warnings:
        lines.extend(f"- {warning}" for warning in result.warnings)
    else:
        lines.append("- None.")

    lines.extend(["", "## Feature Mapping", ""])
    lines.append("| Source feature | Type | Normalization | Direction | Output columns | Notes |")
    lines.append("|---|---|---|---|---:|---|")
    for feature in result.feature_results:
        notes = "; ".join(feature.notes) if feature.notes else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    feature.feature_name,
                    feature.data_type,
                    feature.normalization_method,
                    feature.ideal_direction,
                    str(len(feature.output_columns)),
                    notes,
                ]
            )
            + " |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Universal Feature_data-driven preprocessor.")
    parser.add_argument("--excel", type=Path, default=Path(DEFAULT_EXCEL))
    parser.add_argument("--output", type=Path, default=Path(OUTPUT_CSV))
    parser.add_argument("--data-sheet", default=DATA_SHEET)
    parser.add_argument("--meta-sheet", default=META_SHEET)
    parser.add_argument("--validation-report", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    result = preprocess_workbook(
        excel_path=args.excel,
        output_path=args.output,
        data_sheet=args.data_sheet,
        meta_sheet=args.meta_sheet,
        validation_report=args.validation_report,
    )
    print("Universal preprocessing complete.")
    print(f"Input: {result.excel_path} (rows={result.data_rows})")
    print(f"Included source features: {result.included_feature_count}")
    print(f"Output: {result.output_path} (features={result.output_feature_count})")
    if args.validation_report is not None:
        print(f"Validation report: {args.validation_report}")


if __name__ == "__main__":
    main()
