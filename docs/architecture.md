# Architecture

A map of the system: the runtime surfaces, the end-to-end data flow, what each
package is responsible for, and the file contracts the modules exchange. Read this
first when you need to find where something lives. For the two deep dives see
[`questionnaire_logic.md`](./questionnaire_logic.md) (the survey) and
[`results_page_logic.md`](./results_page_logic.md) (the results dashboard).

---

## 1. Runtime surfaces

There are three Streamlit apps and one command-line pipeline. They share the same
library code under `conjoint/`, `dashboard/`, and `survey_views/`.

| Surface | Entry point | Audience | Reads | Writes |
|---------|-------------|----------|-------|--------|
| Portfolio dashboard | `app.py` | Analyst | `outputs/<dataset>/distance_matrix*.csv`, `nearest_neighbors*.csv`, `importance.csv` | nothing (interactive) |
| Survey app | `survey.py` | Respondent | `questionnaire_spec.json`, a survey workbook | `responses_<id>.csv` (download) |
| Results dashboard | `results_app.py` | Analyst | `outputs/survey_responses_<product>/responses_*.csv` | exported charts / tables |
| CLI pipeline | `preprocessing.py`, `compute_distance_matrix.py`, `conjoint.*`, `run.sh` | Engineer | Excel workbooks, intermediate CSVs | the `outputs/` tree |

The apps are deliberately decoupled. A respondent never touches the analyst
dashboard, and the results dashboard is import-safe (all rendering is behind
`dashboard.results_dashboard.render_results_dashboard`, so it is unit-testable).

---

## 2. End-to-end data flow

```
Excel workbook (Edited + Feature_data)
      │
      │  preprocessing.py            ── Module 1
      ▼
preprocessed_output.csv  +  attribute_column_map.json  +  validation_report_<ds>.md
      │                                   │
      │  compute_distance_matrix.py       │  (attribute -> feature columns map)
      │  (default / technical)            │
      ▼                                   │
distance_matrix.csv                       │
nearest_neighbors.csv ───────────────►  app.py  (technical view)
                                          │
conjoint.generate_questionnaire ── M2     │
      ▼                                   │
questionnaire_spec.json                   │
      │  survey.py  (respondents)         │
      ▼                                   │
responses_<id>.csv  /  acbc_responses.csv │
      │  conjoint.estimate (OLS)          │
      │  conjoint.acbc.estimate (MNL/HB)  │  ── Module 3
      ▼                                   │
importance.csv  (+ utilities.csv)         │
      │                                   │
      │  compute_distance_matrix.py --mode weighted  ── Module 4
      │      --importance importance.csv  │
      │      --attribute-map  ────────────┘
      ▼
distance_matrix_weighted.csv
nearest_neighbors_weighted.csv ───────►  app.py  (customer-weighted view)  ── Module 5
                                          results_app.py  (importance, part-worths, simulator)
```

Two branches start from `preprocessed_output.csv`: the **technical** branch goes
straight to the distance matrix, and the **conjoint** branch routes through the
survey and estimation before re-entering the distance step as weights. The
`attribute_column_map.json` is the glue that lets Module 4 map one conjoint
attribute to the (possibly several, one-hot) feature columns it produced in
Module 1.

---

## 3. Package responsibilities

### `conjoint/`  (estimation core)

| Module | Provides |
|--------|----------|
| `generate_questionnaire.py` | CLI that turns a workbook's `Feature_data` into `questionnaire_spec.json` and an empty `responses.csv` template (Module 2). |
| `questionnaire.py` | The spec model and generation logic behind the CLI. |
| `estimate.py` | OLS-per-respondent estimation: part-worth utilities and relative importance from `responses.csv` (Module 3, ratings path). |
| `io.py` | Shared column names and CSV helpers (e.g. `ATTRIBUTE_COL`, `RELATIVE_IMPORTANCE_COL`). |

### `conjoint/acbc/`  (adaptive choice-based conjoint)

| Module | Provides |
|--------|----------|
| `design.py` | `Profile`, `attribute_levels_from_spec`, `generate_profiles` (balanced design). |
| `screener.py` | `seed_screener_pool`: near-anchor profile perturbations. |
| `tournament.py` | `Task`, `build_tasks`: pair / choice task construction. |
| `byo.py` | Build-your-own anchor selection. |
| `constraints.py` | `split_constraints`, `anchor_from_ratings`, `filter_by_constraints`. |
| `responses.py` | `assemble_*_responses`, `validate_acbc_responses`, `concat_responses`: long-format response assembly and validation. |
| `estimate.py` | MNL fit (`fit_from_responses`) and Hierarchical Bayes (`fit_hb`, Metropolis-within-Gibbs); importance, level utilities, Rhat. |
| `simulation.py` | `share_of_preference`, `aggregate_shares`, `removal_impact`: market simulator. |
| `synthetic.py`, `respondent_sim.py` | Synthetic respondents for tests and demos. |
| `diagnostics.py`, `quality.py` | Convergence and design-quality diagnostics. |

### `dashboard/`  (analysis + rendering)

| Module | Provides |
|--------|----------|
| `viz.py` | Distance-matrix loading, PCA embedding, distance histogram, neighbour bars. |
| `comparison.py` | Side-by-side technical vs weighted neighbours, importance pie, view resolution. |
| `simulation.py` | Product-removal scenarios for the portfolio dashboard. |
| `results_analysis.py` | `analyze_survey_results` -> the immutable `SurveyResults` bundle (two models + five stage statistics). |
| `results_dashboard.py` | `render_results_dashboard`: the seven results panels (`st` injected). |
| `exporting.py` | Chart and dataset export for the results dashboard. |
| `quality_diagnostics.py` | The quality / convergence diagnostics page. |

### `survey_views/`  (one module per survey stage)

`intro`, `part_a_background`, `b0_features`, `b2_constraints`, `acbc_tournament`,
`b5_calibration`, `part_c_wtp`, `acbc_summary`, plus the supporting `navigation`
(sequential page controller), `state` (session-state keys), `theme`,
`spec_source` (loads `questionnaire_spec.json`), and `section_source` (loads Part A
/ bands / Part C from the survey workbook). `acbc_byo` and `acbc_screener` back the
adaptive pool that B4 draws from.

### Other directories

- `smartphone_cleaning/` : `parsers.py`, `extract.py`, `clean.py` decompose noisy
  composite strings into structured numeric features.
- `scripts/` : demo and fixture builders (`build_demo_workbook.py`,
  `build_demo_importance.py`, `make_synthetic_acbc.py`, …) and
  `export_results_pack.py`.
- `validation/` : per-dataset validation reports plus `validate_conjoint.py` and
  `validate_task4.py`.
- `templates/` : the annotated `feature_schema_template.xlsx` and
  `custom_product_template.xlsx`.

---

## 4. File contracts

The modules communicate through a small set of stable files.

| File | Produced by | Shape | Consumed by |
|------|-------------|-------|-------------|
| `preprocessed_output.csv` | `preprocessing.py` | one row per product, numeric feature columns | `compute_distance_matrix.py` |
| `attribute_column_map.json` | `preprocessing.py` | `{attribute: [feature_column, …]}` | weighted distance (Module 4) |
| `questionnaire_spec.json` | `conjoint.generate_questionnaire` | attributes, levels, question types, sections | `survey.py`, `results_app.py` |
| `responses_<id>.csv` | `survey.py` | long format: `(respondent, stage, task_id, alternative_index, …)` | `conjoint(.acbc).estimate`, `results_app.py` |
| `importance.csv` | `conjoint.estimate` / `conjoint.acbc.estimate` | one row per attribute with relative importance | `compute_distance_matrix.py --mode weighted` |
| `utilities.csv` | `conjoint(.acbc).estimate` | per-respondent (HB) or population part-worths | results dashboard simulator |
| `distance_matrix[_weighted].csv` | `compute_distance_matrix.py` | square symmetric matrix | `app.py` |

The OLS and ACBC estimators write the **same** `importance.csv` schema, which is
why Module 4 is unchanged whichever estimation path produced it.

---

## 5. Configuration

Most behaviour is data-driven rather than coded.

- **Survey product selection.** `survey.py` and `results_app.py` resolve their
  spec and workbook in this order: `?spec=<path>` query param, then `SURVEY_SPEC` /
  `SURVEY_WORKBOOK` environment variables, then the bundled defaults. Both loaders
  are fail-soft: a missing or invalid source logs a warning and falls back to the
  built-in defaults so the app never crashes.
- **Dataset discovery.** The results dashboard auto-discovers any
  `outputs/survey_responses_<product>/` folder, so adding a product is a matter of
  dropping its responses in place.
- **Distance label column.** `compute_distance_matrix.py` auto-detects the product
  label from `product_id`, `product`, `model`, then `brand`; override with
  `--product-col`.

---

## 6. Adding a dataset

1. Build a workbook that satisfies the schema in
   [`../../Docs/attribute_schema.md`](../../Docs/attribute_schema.md), starting from
   `templates/feature_schema_template.xlsx`.
2. `python preprocessing.py --excel your_file.xlsx` (writes
   `preprocessed_output.csv`, `attribute_column_map.json`, and a validation report).
3. `python compute_distance_matrix.py --excel your_file.xlsx` for the technical
   view; add the conjoint steps (Modules 2 to 4) for the customer-weighted view.
4. File the results under `outputs/<dataset>/`. The dashboards pick the folder up
   automatically.

See [`../SETUP.md`](../SETUP.md) for the copy-paste version.
