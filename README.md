# Distance-Analysis

## Input Data
By default, the tool uses the tractor dataset in `Database_Distance Analysis.xlsx`.

The tool also supports user-uploaded product data via an Excel template:
- `templates/custom_product_template.xlsx`

The Excel file must contain two sheets:
- `Edited`
- `Feature_data`

## Running the Tool

### Default (tractor dataset)
```bash
python preprocessing.py
python compute_distance_matrix.py
```
### User-uploaded product portfolio:
```bash
python preprocessing.py --excel <your_file.xlsx>
python compute_distance_matrix.py --excel <your_file.xlsx>
```

`preprocessing.py` is the universal preprocessor for all product categories.
It reads the workbook's `Edited` and `Feature_data` sheets, applies the
metadata rules, and writes one numeric `preprocessed_output.csv` for the
distance step.
`compute_distance_matrix.py` auto-detects the product label column from
`product_id`, `product`, `model`, then `brand`; override with
`--product-col` if needed.
## Output
The tool generates:
- preprocessed_output.csv
- distance_matrix.csv
- nearest_neighbors.csv
- distance_summary.txt


## Dashboard

The project includes an interactive Streamlit dashboard for exploring the product portfolio and simulating product removal scenarios.

Run the dashboard with:

```bash
python -m streamlit run app.py
