# Universal Preprocessor Validation — smart phone dataset (cleaned).xlsx

## Summary
- Workbook: `smart phone dataset (cleaned).xlsx`
- Output: `preprocessed_output.csv`
- Input rows: 1020
- Raw columns in `Edited`: 16
- Metadata rows used: 15
- Included source features: 15
- Output numeric features: 27

## Warnings
- None.

## Feature Mapping

| Source feature | Type | Normalization | Direction | Output columns | Notes |
|---|---|---|---|---:|---|
| price | metric | z-score | lower | 1 |  |
| rating | metric | min-max | higher | 1 | 141 value(s) parsed as missing and imputed. |
| processor_ghz | metric | min-max | higher | 1 | 70 value(s) parsed as missing and imputed. |
| processor_cores | ordinal | min-max | higher | 1 | 38 value(s) parsed as missing and imputed. |
| chip_brand | nominal | none | neutral | 9 |  |
| ram_gb | metric | min-max | higher | 1 | 10 value(s) parsed as missing and imputed. |
| storage_gb | metric | min-max | higher | 1 | 5 value(s) parsed as missing and imputed. |
| battery_mah | metric | min-max | higher | 1 | 12 value(s) parsed as missing and imputed. |
| display_size_in | metric | min-max | higher | 1 |  |
| display_refresh_hz | ordinal | min-max | higher | 1 |  |
| camera_main_mp | metric | min-max | higher | 1 | 1 value(s) parsed as missing and imputed. |
| camera_front_mp | metric | min-max | higher | 1 | 38 value(s) parsed as missing and imputed. |
| camera_rear_count | ordinal | min-max | higher | 1 |  |
| card_supported | binary | none | higher | 1 |  |
| os_family | nominal | none | neutral | 5 |  |
