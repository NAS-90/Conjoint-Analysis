# Universal Preprocessor Validation — smart phone dataset.xlsx

## Summary
- Workbook: `smart phone dataset.xlsx`
- Output: `preprocessed_output.csv`
- Input rows: 1020
- Raw columns in `Edited`: 11
- Metadata rows used: 9
- Included source features: 9
- Output numeric features: 351

## Warnings
- ram: ordinal feature has normalization_method=none; using parsed ordinal values.
- battery: ordinal feature has normalization_method=none; using parsed ordinal values.
- display: ordinal feature has normalization_method=none; using parsed ordinal values.
- camera: ordinal feature has normalization_method=none; using parsed ordinal values.

## Feature Mapping

| Source feature | Type | Normalization | Direction | Output columns | Notes |
|---|---|---|---|---:|---|
| price | metric | z-score | lower | 1 |  |
| rating | metric | min-max | higher | 1 | 141 value(s) parsed as missing and imputed. |
| processor | nominal | none | neutral | 296 |  |
| ram | ordinal | none | higher | 1 | 1 value(s) parsed as missing and imputed. |
| battery | ordinal | none | higher | 1 | 1 value(s) parsed as missing and imputed. |
| display | ordinal | none | higher | 1 | 7 value(s) parsed as missing and imputed. |
| camera | ordinal | none | higher | 1 | 49 value(s) parsed as missing and imputed. |
| card | binary | none | higher | 1 |  |
| os | nominal | none | neutral | 48 |  |
