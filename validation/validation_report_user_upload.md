## Setup

- Repository: Selensta/Distance-Analysis
- Scripts executed:
  - preprocessing.py --excel "templates/custom_product_template.xlsx" → preprocessed_output.csv
  - compute_distance_matrix.py --excel "templates/custom_product_template.xlsx" → distance_matrix.csv, nearest_neighbors.csv, distance_summary.txt
- Distance metric: Euclidean
- Feature scaling: StandardScaler (SCALE_ALL_FEATURES = True)

- Input after preprocessing: n = 3 products, d = 7 features (after encoding)
- Distance matrix output: distance_matrix.csv (3 x 3)
- Nearest neighbors output: nearest_neighbors.csv (top_k = 5)

---

## Technical validation (via validation/validate_task4.py)

- N (products): 3
- Diagonal max abs: 0.0
- Symmetry max abs: 0.0
- Min value: 0.0
- Max value: 5.718362951410651
- NaN count: 0
- Inf count: 0

Result: The output satisfies the required properties of a valid Euclidean distance matrix (square, symmetric, zero diagonal, finite values).

---

## Plausibility validation (nearest neighbors)

Observed behavior:

- Bike_A ↔ Bike_B show the smallest distance (~3.01).
- Bike_C is significantly farther from both (~5.95–6.05).
- Similar specifications (carbon frame, 28", disc brakes) yield smaller distances.
- Structural differences (aluminum frame, heavier weight, no disc brakes) yield larger distances.

This behavior is consistent with expected product similarity.

---

## Conclusion

The user-upload bicycle dataset runs successfully end-to-end, produces a technically valid distance matrix, and nearest-neighbor results behave plausibly.
