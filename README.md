# Distance-Analysis

A product-portfolio analysis tool that measures **how similar products are to each
other**, and then re-frames that similarity through the eyes of the **customer**.

The tool starts from a product list (tractors, smartphones, or any uploaded
catalogue), turns the raw spec sheet into a clean numeric matrix, and computes the
pairwise distance between every product. Managers use this to spot overlaps in a
portfolio, find empty gaps in a market, and simulate what happens when a product is
removed. On top of this *technical* distance, the tool adds a **Conjoint Analysis**
layer: it runs a survey, learns how much each attribute actually matters to buyers,
and re-weights the distance so it reflects *customer-perceived* similarity rather
than raw engineering specs.

> Two products can look almost identical on paper yet feel very different to a buyer
> if the features that matter most to them differ. The technical view answers
> "which products are similar by spec?"; the customer-weighted view answers "which
> products are similar in the eyes of the customer?".

This repository is the project-study deliverable for *"Adding Customer Preferences
to the Distance Analysis Tool"* (TUM). For the project background, scope, and
timeline see [`../Docs/Expose_v3.md`](../Docs/Expose_v3.md).

---

## Contents

- [The big picture](#the-big-picture)
- [Quickstart](#quickstart)
- [The Streamlit apps](#the-streamlit-apps)
- [Input data format](#input-data-format)
- [The pipeline, step by step](#the-pipeline-step-by-step)
- [Outputs](#outputs)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Documentation](#documentation)

---

## The big picture

The work is organized as five modules, each writing a file the next one reads. This
follows the original `preprocessing -> distance matrix -> dashboard` flow and
extends it with the conjoint layer.

| # | Module | What it does | Entry point |
|---|--------|--------------|-------------|
| 1 | Universal Preprocessor | Reads any workbook via its `Feature_data` sheet and emits one numeric matrix. | `preprocessing.py` |
| 2 | Survey Setup + Questionnaire Generator | Creates the survey-question workbook and turns attribute metadata into a survey spec. | `survey_setup_bundle/survey_setup.py`, `conjoint.generate_questionnaire`, `survey.py` |
| 3 | Conjoint Computation | Estimates part-worth utilities and relative importance from the survey answers. | `conjoint.estimate`, `conjoint.acbc.estimate` |
| 4 | Weighted Distance | Re-scales each attribute by its importance before computing distances. | `compute_distance_matrix.py --mode weighted` |
| 5 | Comparative Dashboard | Shows the technical and customer-weighted views side by side. | `app.py`, `results_app.py` |

```
                      ┌──────────────────────────────────────────────┐
                      │  Excel workbook                              │
                      │  Edited sheet (products) + Feature_data sheet │
                      └───────────────────────┬──────────────────────┘
                                              │  preprocessing.py  (Module 1)
                                              ▼
                                  preprocessed_output.csv
                            ┌─────────────────┴──────────────────┐
                            |                                    |
                            |                                    ▼
                            |                            survey_setup.py       
       compute_distance_    │                                    │  conjoint.generate_questionnaire (M2)
       matrix.py (M1 tech)  ▼                                    ▼
                  distance_matrix.csv                    questionnaire_spec.json
                  nearest_neighbors.csv                          │  survey.py  (collect answers)
                            │                                    ▼
                            │                            responses_*.csv
                            │                                    │  conjoint(.acbc).estimate (M3)
                            │                                    ▼
                            │                              importance.csv
                            │   compute_distance_matrix.py --mode weighted (M4)
                            └───────────────┬────────────────────┘
                                            ▼
                            distance_matrix_weighted.csv
                                            │  app.py / results_app.py  (Module 5)
                                            ▼
                          Technical  |  Customer-weighted   dashboards
```

---

## Quickstart

Prerequisites and per-OS install notes live in [`SETUP.md`](SETUP.md). The short
version (macOS / Linux, Python 3.11 or 3.12):

```bash
chmod +x run.sh        # first time only
./run.sh               # venv + deps + regenerate all outputs + launch the dashboard
```

The dashboard opens at <http://localhost:8501>. Each phase can also be run on its
own:

```bash
./run.sh setup         # create .venv and install requirements.txt
./run.sh preprocess    # regenerate outputs/ for tractors, smartphones, user upload
./run.sh conjoint      # build the conjoint demo + customer-weighted distances
./run.sh app           # launch the portfolio dashboard (app.py)
./run.sh survey        # launch the standalone questionnaire app (survey.py)
```

---

## The Streamlit apps

The project ships three main Streamlit apps plus a small setup helper. They are
decoupled on purpose: analysts and survey respondents use different URLs.

### Optional survey setup helper, `survey_setup_bundle/survey_setup.py`

```bash
python -m streamlit run survey_setup_bundle/survey_setup.py
```

Use this before launching the respondent survey when you need to create the
active `survey_questions.xlsx`. It asks for a product name and six Section C
features, lets you review the generated prompts, and saves the workbook that
`survey.py` reads by default.

### 1. Portfolio dashboard, `app.py`

```bash
python -m streamlit run app.py        # or: ./run.sh app
```

The analyst-facing dashboard. Pick a product category (Smartphones, Tractors, User
Upload, Conjoint Demo) and explore the distance matrix: nearest-neighbour tables, a
distance histogram, a 2D/3D PCA embedding, and a **Product Removal** simulator. A
**Technical | Customer-weighted** toggle switches between the two distance views;
the Conjoint Demo dataset carries real conjoint weights, so its customer-weighted
view is fully populated.

### 2. Survey app, `survey.py`

```bash
python -m streamlit run survey.py     # or: ./run.sh survey
```

The respondent-facing questionnaire. It renders one linear flow modelled on the
reference Part A / B / C design, with its own `st.navigation` router:

```
Welcome -> Part A -> B0 -> B2 -> B4 -> B5 -> Part C -> Thank you
```

- **Part A** background and screening (profiling only, not part of estimation).
- **B0** explains every attribute and its levels.
- **B2** captures must-have / unacceptable constraints and derives an ideal anchor.
- **B4** pairwise choice tasks (the core conjoint signal).
- **B5** 0 to 5 purchase-probability calibration.
- **Part C** willingness-to-pay for upgrades.

On finish it downloads one long-format `responses_<id>.csv`. The flow is entirely
data-driven from `questionnaire_spec.json` plus a survey workbook, so switching
products needs no code change. See
[`docs/questionnaire_logic.md`](docs/questionnaire_logic.md) for the full
design-to-code mapping.

### 3. Results dashboard, `results_app.py`

```bash
python -m streamlit run results_app.py
# or, for the computer/laptop product set:
SURVEY_SPEC=questionnaire_spec_computers.json \
SURVEY_WORKBOOK=computer_survey_questions.xlsx \
  python -m streamlit run results_app.py
```

Loads the per-respondent `responses_*.csv` files (from a local folder or an
upload), fits MNL plus Hierarchical Bayes, and presents seven panels: overview and
convergence, attribute importance, part-worth utilities, willingness-to-pay, a
market simulator, purchase likelihood, and respondent segments. See
[`docs/results_page_logic.md`](docs/results_page_logic.md) for how each chart is
computed.

---

## Input data format

Every workbook must contain exactly two sheets:

| Sheet | Role |
|-------|------|
| `Edited` | One product per row. First column is `product_id` (string, unique). Remaining columns match the `feature_name` entries in `Feature_data`. |
| `Feature_data` | One row per feature, describing its type, normalization, ideal direction, and conjoint role. |

`Feature_data` is the metadata that drives everything downstream: which columns
enter the distance, how each is normalized, and which become conjoint attributes
(with their levels and question type). The full column contract, validation rules,
and worked examples are in [`../Docs/attribute_schema.md`](../Docs/attribute_schema.md).
The easiest way to start a new dataset is the annotated template at
[`templates/feature_schema_template.xlsx`](templates/feature_schema_template.xlsx),
which ships with per-column help comments and dropdown validation.

By default the tool uses the bundled tractor dataset
(`Database_Distance Analysis.xlsx`).

---

## The pipeline, step by step

### Module 1: preprocessing (technical distance)

`preprocessing.py` is the universal preprocessor for every product category. It
reads the `Edited` and `Feature_data` sheets, applies the metadata rules
(z-score / min-max / ordinal-mapping, one-hot for nominal columns), and writes a
single numeric `preprocessed_output.csv`.

```bash
# Default tractor dataset
python preprocessing.py
python compute_distance_matrix.py

# Any workbook
python preprocessing.py --excel <your_file.xlsx>
python compute_distance_matrix.py --excel <your_file.xlsx>
```

`compute_distance_matrix.py` auto-detects the product label column from
`product_id`, `product`, `model`, then `brand`; override with `--product-col` when
needed.

### Smartphone cleaning (noisy composite strings)

The raw `smart phone dataset.xlsx` stores composite attributes as free text (camera
`"50 MP + 8 MP + 2 MP Triple Rear & 16 MP Front Camera"`, display
`"6.7 inches, 1440 x 3216 px, 120 Hz …"`) and has column-shifted feature-phone
rows. Feeding these verbatim distorts similarity. Run the cleaner first:

```bash
python clean_smartphones.py \
    --input "smart phone dataset.xlsx" \
    --output "smart phone dataset (cleaned).xlsx"
python preprocessing.py --excel "smart phone dataset (cleaned).xlsx"
```

It decomposes each composite string into structured numeric features
(`camera_main_mp`, `display_size_in`, `display_refresh_hz`, `processor_ghz`,
`ram_gb`, `storage_gb`, `battery_mah`, `chip_brand`, `os_family`, …) by content,
not column position, so shifted rows realign automatically. Output drops from 351
noisy columns to 27 meaningful ones.

### Modules 2 to 5: customer-weighted distance

The full conjoint chain re-scales each attribute by its conjoint relative
importance:

```bash
# 2. Generate a questionnaire from a workbook's Feature_data sheet
python -m conjoint.generate_questionnaire \
    --excel conjoint_demo.xlsx \
    --out questionnaire_spec.json \
    --responses-template responses_template.csv

# 3a. Collect ratings: fill responses_template.csv by hand, or run survey.py
#     and download a contract-compliant responses.csv.

# 3b. Estimate part-worths + importance
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
# -> distance_matrix_weighted.csv, nearest_neighbors_weighted.csv

# 5. Explore in the dashboard's Technical | Customer-weighted toggle.
```

`./run.sh conjoint` automates all of this for a bundled, authentic demo
(`conjoint_demo.xlsx`, weighted by the real published N=381 tractor study) and
writes everything to `outputs/conjoint_demo/`. See
[`validation/validation_report_conjoint.md`](validation/validation_report_conjoint.md)
for the technical-vs-weighted comparison.

### ACBC pipeline (MNL + Hierarchical Bayes)

The survey app's adaptive flow produces a long-format `acbc_responses.csv` that is
estimated with a multinomial-logit model, optionally with per-respondent
Hierarchical-Bayes betas:

```bash
# Population MNL only
python -m conjoint.acbc.estimate \
    --responses acbc_responses.csv \
    --out-importance importance.csv \
    --out-utilities population_utilities.json

# With Hierarchical-Bayes per-respondent betas
python -m conjoint.acbc.estimate \
    --responses acbc_responses.csv \
    --hb --hb-iter 4000 --hb-burnin 2000 \
    --out-importance importance.csv \
    --out-hb-utilities utilities.csv
```

The output `importance.csv` matches the OLS schema, so
`compute_distance_matrix.py --mode weighted` consumes it unchanged. For the
algorithmic detail (effects coding, level balance, MNL log-likelihood, HB Gibbs
sampler, share-of-preference, removal impact) see
[`docs/acbc_design_spec.md`](docs/acbc_design_spec.md).

### Results pack (report / slides)

To bundle the headline conjoint results for the report and slide deck:

```bash
python scripts/export_results_pack.py
```

This writes `outputs/report_pack/` with the relative-importance table (CSV plus a
markdown comparison against the published N=381 reference), a
technical-vs-customer-weighted top-3 neighbour comparison for every configuration,
offline Plotly figures (`importance_pie.html`, `neighbor_shift_bar.html`), and a
copy of the validation report.

---

## Outputs

A preprocessing + distance run produces:

- `preprocessed_output.csv` : the numeric feature matrix.
- `distance_matrix.csv` : the full pairwise distance matrix.
- `nearest_neighbors.csv` : the closest products to each product.
- `distance_summary.txt` : a human-readable summary.

The weighted run adds `distance_matrix_weighted.csv` and
`nearest_neighbors_weighted.csv`. `./run.sh` files everything per dataset under
`outputs/{tractors,smartphones,user_upload,conjoint_demo}/`.

---

## Project layout

```
Distance-Analysis/
├── app.py                      # Module 5: portfolio dashboard (technical | weighted)
├── survey.py                   # Module 2: respondent questionnaire app
├── survey_setup_bundle/        # optional setup app for survey_questions.xlsx
├── results_app.py              # conjoint results dashboard (MNL + HB)
├── preprocessing.py            # Module 1: universal Feature_data-driven preprocessor
├── compute_distance_matrix.py  # Modules 1/4: technical and weighted distance
├── clean_smartphones.py        # smartphone composite-string cleaner
├── run.sh                      # bootstrap + launcher
├── conjoint/                   # conjoint estimation
│   ├── generate_questionnaire.py, questionnaire.py, estimate.py, io.py
│   └── acbc/                   # adaptive CBC: design, screener, tournament, byo,
│                               #   constraints, responses, estimate, simulation, …
├── dashboard/                  # dashboard rendering + analysis (viz, comparison,
│                               #   results_dashboard, results_analysis, simulation, exporting)
├── survey_views/               # one module per survey stage + navigation controller
├── smartphone_cleaning/        # composite-attribute parsers
├── scripts/                    # demo builders, fixtures, results-pack export
├── validation/                 # per-dataset validation reports + validators
├── templates/                  # feature-schema and custom-product Excel templates
├── docs/                       # design docs (see Documentation below)
└── tests/                      # 35 pytest modules
```

A few standalone scripts at the top level (`distance_matrix.py`,
`feature_analysis.py`, `portfolio_view.py`, `dataset_selector.py`,
`product_lookup.py`, `simulation.py`, `preprocessing_smartphones.py`) are earlier
single-purpose utilities kept for reference; the supported entry points are the
ones listed above and in `run.sh`.

---

## Testing

The suite uses pytest (35 test modules) and runs in CI on every push and pull
request (`.github/workflows/ci.yml`, Python 3.12).

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                       # full suite
pytest -m unit               # fast unit tests only
pytest --cov=. --cov-report=term-missing
```

---

## Documentation

| Doc | What it covers |
|-----|----------------|
| [`SETUP.md`](SETUP.md) | Install, one-command bootstrap, troubleshooting, adding a dataset |
| [`docs/architecture.md`](docs/architecture.md) | System overview, data flow, module and file map |
| [`docs/questionnaire_logic.md`](docs/questionnaire_logic.md) | Survey design to code: every stage of `survey.py` |
| [`docs/results_page_logic.md`](docs/results_page_logic.md) | How each results-dashboard chart is computed |
| [`docs/acbc_design_spec.md`](docs/acbc_design_spec.md) | ACBC algorithm: effects coding, MNL, HB Gibbs sampler |
| [`../Docs/attribute_schema.md`](../Docs/attribute_schema.md) | The `Feature_data` schema contract |
| [`../Docs/algorithm_spec.md`](../Docs/algorithm_spec.md) | Conjoint math: OLS, aggregation, weighted distance |
| [`../Docs/Expose_v3.md`](../Docs/Expose_v3.md) | Project background, modules, timeline, roles |
