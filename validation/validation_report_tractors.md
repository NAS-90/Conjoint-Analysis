# Task 4 – Validation of Distance Prototype

## Setup
- Repository: bingying-wu/Distance-Analysis
- Scripts executed:
  - preprocessing.py (universal `Feature_data` preprocessor) → preprocessed_output.csv
  - compute_distance_matrix.py → distance_matrix.csv, nearest_neighbors.csv, distance_summary.txt
- Distance metric: Euclidean
- Input after preprocessing: n = 166 products, d = 43 features (after encoding)
- Distance matrix output: distance_matrix.csv (166 × 166)
- Nearest neighbors output: nearest_neighbors.csv (top_k = 5)

## Technical validation (via validation/validate_task4.py)
- N (products): 166
- Diagonal max abs: 0.0
- Symmetry max abs: 0.0
- Min value: 0.0
- Max value: 21.017633973350147
- NaN count: 0
- Inf count: 0

Result: The output satisfies the required properties of a valid Euclidean distance matrix (square, symmetric, zero diagonal, finite values).

## Plausibility validation (nearest neighbors)
A nearest-neighbor excerpt (3 reference products × 5 neighbors) is provided in:
- validation/neighbors_sample.csv

Observed behavior in the sample:
- Identical variants show distance = 0.0 (e.g., Essential II vs Essential III).
- Small spec changes show small distances (e.g., 67hp → 75hp gives ≈ 0.6768–0.7110).
- Larger configuration changes yield much larger distances (e.g., ≈ 7.8941), which is consistent with expected dissimilarity.

## Conclusion
The prototype runs successfully, produces a technically valid distance matrix, and the nearest-neighbor results behave plausibly on sample products.
