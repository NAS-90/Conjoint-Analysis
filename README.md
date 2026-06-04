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

### Smartphone data cleaning (noisy composite strings)

The raw `smart phone dataset.xlsx` stores composite attributes as free text
(camera `"50 MP + 8 MP + 2 MP Triple Rear & 16 MP Front Camera"`, display
`"6.7 inches, 1440 x 3216 px, 120 Hz …"`) and has column-shifted feature-phone
rows. Feeding these verbatim distorts similarity (the `processor`/`os` columns
alone exploded into ~344 one-hot junk dimensions). Run the cleaner first:

```bash
python clean_smartphones.py \
    --input "smart phone dataset.xlsx" \
    --output "smart phone dataset (cleaned).xlsx"
python preprocessing.py --excel "smart phone dataset (cleaned).xlsx"
```

It decomposes each composite string into structured numeric features
(`camera_main_mp`, `display_size_in`, `display_refresh_hz`, `processor_ghz`,
`ram_gb`, `storage_gb`, `battery_mah`, `chip_brand`, `os_family`, …) by content
(not column position), so shifted rows are realigned automatically. Output
drops from 351 noisy columns to 27 meaningful ones. `./run.sh preprocess` wires
this in for the smartphone dataset.
`compute_distance_matrix.py` auto-detects the product label column from
`product_id`, `product`, `model`, then `brand`; override with
`--product-col` if needed.
## Output
The tool generates:
- preprocessed_output.csv
- distance_matrix.csv
- nearest_neighbors.csv
- distance_summary.txt


## Conjoint customer-weighted analysis

Beyond the *technical* (uniform) distance, the tool supports a
*customer-weighted* distance that re-scales each attribute by its conjoint
relative importance. The full chain (Modules 2–5):

```bash
# 1. Generate a questionnaire from a workbook's Feature_data sheet
python -m conjoint.generate_questionnaire \
    --excel conjoint_demo.xlsx \
    --out questionnaire_spec.json \
    --responses-template responses_template.csv

# 2. Collect ratings → responses.csv
#    - fill responses_template.csv by hand, OR
#    - run the standalone survey app (./run.sh survey, or streamlit run survey.py)
#      to enter 1..5 ratings and download a contract-compliant responses.csv.

# 3. Estimate part-worths + importance (OLS → aggregate)
python -m conjoint.estimate \
    --responses responses.csv \
    --out-utilities utilities.csv \
    --out-importance importance.csv

# 4. Customer-weighted distance (needs importance.csv + attribute_column_map.json)
python preprocessing.py --excel conjoint_demo.xlsx \
    --attribute-map attribute_column_map.json
python compute_distance_matrix.py --excel conjoint_demo.xlsx \
    --product-col product_id \
    --mode weighted \
    --importance importance.csv \
    --attribute-map attribute_column_map.json
# → distance_matrix_weighted.csv, nearest_neighbors_weighted.csv

# 5. Explore in the dashboard's Technical | Customer-weighted toggle.
```

`./run.sh conjoint` automates all of this for a bundled, authentic demo
(`conjoint_demo.xlsx`, weighted by the **real** published N=381 tractor study)
and writes everything to `outputs/conjoint_demo/`. See
`validation/validation_report_conjoint.md` for the technical-vs-weighted
comparison.

## Results pack (report / slides)

To bundle the headline conjoint results for the report and slide deck, run:

```bash
python scripts/export_results_pack.py
```

This writes `outputs/report_pack/` with the relative-importance table (CSV +
markdown vs the published N=381 reference), a technical-vs-customer-weighted
top-3 neighbour comparison for every configuration, offline Plotly figures
(`importance_pie.html`, `neighbor_shift_bar.html`), and a copy of the
validation report. Open the `.html` figures in a browser; print to PDF for the
report appendix if needed.

## Dashboard

The project includes an interactive Streamlit dashboard for exploring the product portfolio and simulating product removal scenarios. It has a **Technical | Customer-weighted** distance toggle.

Run the dashboard with:

```bash
python -m streamlit run app.py   # or: ./run.sh app
```

## Survey app

The conjoint **questionnaire** is a separate Streamlit app with its own
`st.navigation` router (`survey.py`), decoupled from the dashboard. It ships
with a committed `questionnaire_spec.json` (generated from `conjoint_demo.xlsx`),
so it works out of the box. The intro page lets the respondent pick one of two
modes:

1. **Part B-1 ratings (OLS)** — single-page-per-attribute 1..5 desirability
   ratings. Downloads `responses.csv` for `python -m conjoint.estimate`.
2. **ACBC BYO → Screener → Tournament (MNL)** — the full adaptive
   choice-based conjoint flow:
   * **BYO** picks a preferred level per attribute (anchor).
   * **Screener** Yes/No filters a pool of profiles seeded around the
     anchor.
   * **Tournament** shows the survivors in choice tasks
     (single-page-per-task).
   The **Summary** route stitches the three stages into a long-format
   `acbc_responses.csv` consumed by `python -m conjoint.acbc.estimate`.

```bash
./run.sh survey                  # or: python -m streamlit run survey.py
```

The view code lives in `survey_views/` (intro, ratings, ACBC stages,
shared navigation controller). The spec itself can be regenerated for any
workbook with `python -m conjoint.generate_questionnaire --excel <wb>
--out questionnaire_spec.json`.

## ACBC pipeline (MNL + HB)

After collecting `acbc_responses.csv` from the survey app, estimate
utilities + importance with:

```bash
# Population MNL only:
python -m conjoint.acbc.estimate \
    --responses acbc_responses.csv \
    --out-importance importance.csv \
    --out-utilities population_utilities.json

# With Hierarchical-Bayes per-respondent betas:
python -m conjoint.acbc.estimate \
    --responses acbc_responses.csv \
    --hb --hb-iter 4000 --hb-burnin 2000 \
    --out-importance importance.csv \
    --out-hb-utilities utilities.csv
```

The output `importance.csv` matches the OLS schema so the existing
`compute_distance_matrix.py --mode weighted` consumes it unchanged. The
dashboard's **Product Removal** panel now adds a before/after pairwise-
distance histogram and a logit share-of-preference transfer table when a
`utilities.csv` is present.

For the algorithmic detail (effects coding, level balance, MNL
log-likelihood, HB Gibbs sampler, share-of-preference, removal impact)
see [`docs/acbc_design_spec.md`](docs/acbc_design_spec.md).
