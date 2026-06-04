# Universal Preprocessor Validation — Database_Distance Analysis.xlsx

## Summary
- Workbook: `Database_Distance Analysis.xlsx`
- Output: `preprocessed_output.csv`
- Input rows: 166
- Raw columns in `Edited`: 31
- Metadata rows used: 30
- Included source features: 26
- Output numeric features: 43

## Warnings
- brand: identifier column forced to conjoint_role=identifier (rule 10).
- product: identifier column forced to conjoint_role=identifier (rule 10).
- class: identifier column forced to conjoint_role=identifier (rule 10).
- model: identifier column forced to conjoint_role=identifier (rule 10).

## Feature Mapping

| Source feature | Type | Normalization | Direction | Output columns | Notes |
|---|---|---|---|---:|---|
| hp_range | ordinal | ordinal-mapping | higher | 1 |  |
| fruityard | binary | none | neutral | 1 |  |
| maximum | metric | z-score | higher | 1 |  |
| number_of_gears | ordinal | ordinal-mapping | higher | 1 |  |
| shuttle | nominal | none | neutral | 4 |  |
| shift_position | nominal | none | neutral | 2 |  |
| transmission_type | nominal | none | neutral | 3 |  |
| injection_types | nominal | none | neutral | 2 |  |
| lifting_capacity | metric | z-score | higher | 1 |  |
| maximum_flow | metric | z-score | higher | 1 |  |
| maximum_torque | metric | z-score | higher | 1 |  |
| memo_speed_function | binary | none | neutral | 1 |  |
| vcr | binary | none | neutral | 1 |  |
| operator_environment | nominal | none | neutral | 3 |  |
| rated_pto_speed | metric | z-score | higher | 1 |  |
| seat_suspension | nominal | none | neutral | 2 |  |
| control_interface | nominal | none | neutral | 3 |  |
| guidance_function | binary | none | neutral | 1 |  |
| steering_wheel_adjustment | nominal | none | neutral | 3 |  |
| tank_capacity | metric | z-score | higher | 1 |  |
| telemetry | binary | none | neutral | 1 |  |
| turning_radius | metric | min-max | lower | 1 | 16 value(s) parsed as missing and imputed. |
| dashboard | nominal | none | neutral | 2 |  |
| weight | metric | z-score | neutral | 1 |  |
| outside_control | nominal | none | neutral | 3 |  |
| wheelbase | metric | z-score | neutral | 1 | 4 value(s) parsed as missing and imputed. |
