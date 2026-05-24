# Universal Preprocessor Validation — custom_product_template.xlsx

## Summary
- Workbook: `templates/custom_product_template.xlsx`
- Output: `preprocessed_output.csv`
- Input rows: 3
- Raw columns in `Edited`: 7
- Metadata rows used: 6
- Included source features: 6
- Output numeric features: 7

## Warnings
- Dropped 1 duplicated header row(s) from Feature_data.
- gears: ordinal feature has normalization_method=none; using parsed ordinal values.

## Feature Mapping

| Source feature | Type | Normalization | Direction | Output columns | Notes |
|---|---|---|---|---:|---|
| price | metric | min-max | lower | 1 |  |
| weight | metric | min-max | lower | 1 |  |
| wheel_size | metric | min-max | higher | 1 |  |
| frame_material | nominal | none | neutral | 2 |  |
| disc_brakes | binary | none | neutral | 1 |  |
| gears | ordinal | none | neutral | 1 |  |
