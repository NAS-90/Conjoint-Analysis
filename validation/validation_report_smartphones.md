## Setup

- Repository: Selennsta/Distance-Analysis
- Scripts executed:
  - preprocessing.py (universal `Feature_data` preprocessor) → preprocessed_output.csv
  - compute_distance_matrix.py → distance_matrix.csv, nearest_neighbors.csv, distance_summary.txt
- Distance metric: Euclidean
- Feature scaling: StandardScaler (SCALE_ALL_FEATURES = True)

- Input after preprocessing: n = 1020 products, d = 351 features (after encoding)
- Distance matrix output: distance_matrix.csv (1020 × 1020)
- Nearest neighbors output: nearest_neighbors.csv (top_k = 5)

## Technical validation (via validation/validate_task4.py)

- N (products): 1020
- Diagonal max abs: 0.0
- Symmetry max abs: 0.0
- Min value: 0.0
- Max value: 67.51922159905743
- NaN count: 0
- Inf count: 0

Result: The output satisfies the required properties of a valid Euclidean distance matrix (square, symmetric, zero diagonal, finite values).

## Plausibility validation (nearest neighbors)

Observed behavior in the sample:

- Identical or near-identical variants show very small distances.
- Minor configuration differences produce small distances.
- Devices across brands or performance classes yield significantly larger distances.
- Some pairs produce distance ≈ 0, indicating identical preprocessed feature vectors.

This behavior is consistent with expected product similarity.

## Conclusion

The smartphone dataset runs successfully end-to-end, produces a technically valid distance matrix, and nearest-neighbor results behave plausibly.
