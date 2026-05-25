# Setup — Distance-Analysis

This guide gets the existing tool running on a fresh checkout. Target audience: any teammate (Mark, Yongheng, Beibei, Jeff, Rick). Tested on macOS and Linux; for Windows, use WSL or translate the commands to PowerShell.

---

## Prerequisites

- **Python 3.12** (3.11 also works). Check with `python3 -V`.
- **Git** (already cloned if you're reading this).
- **~500 MB free disk** for the venv + intermediate CSVs.

If you don't have Python 3.12 installed:

| OS | Install |
|---|---|
| macOS | `brew install python@3.12` |
| Ubuntu/Debian | `sudo apt install python3.12 python3.12-venv` |
| Windows | Install from <https://www.python.org/downloads/> and check "Add to PATH" |

---

## One-command bootstrap

From the repo root (`Distance-Analysis/`):

```bash
chmod +x run.sh        # first time only
./run.sh               # creates venv, installs deps, regenerates outputs/, launches dashboard
```

The dashboard opens at <http://localhost:8501>. Press `Ctrl-C` to stop it.

### What `./run.sh` does

1. **setup** — creates `.venv/`, installs everything in `requirements.txt`.
2. **preprocess** — runs the universal `Feature_data`-driven preprocessor for all three datasets, writing outputs (including an `attribute_column_map.json` per dataset) to `outputs/{tractors,smartphones,user_upload}/`.
3. **conjoint** — builds the authentic conjoint demo (`conjoint_demo.xlsx`, weighted by the real published N=381 tractor study), computes its technical + customer-weighted distances into `outputs/conjoint_demo/`, opportunistically adds a weighted view to any other dataset that carries conjoint attributes, and regenerates `validation/validation_report_conjoint.md`.
4. **app** — launches `streamlit run app.py`.

You can run each phase independently:

```bash
./run.sh setup        # only create venv + install deps
./run.sh preprocess   # only regenerate outputs/ (incl. attribute maps)
./run.sh conjoint     # only build the conjoint demo + customer-weighted distances
./run.sh app          # only launch streamlit (needs venv + outputs/)
```

---

## Manual setup (if `run.sh` is not an option)

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# regenerate outputs
python preprocessing.py
python compute_distance_matrix.py
mkdir -p outputs/tractors && mv preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/tractors/

python preprocessing.py --excel "smart phone dataset.xlsx"
python compute_distance_matrix.py --excel "smart phone dataset.xlsx" --product-col model
mkdir -p outputs/smartphones && mv preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/smartphones/

# launch dashboard
python -m streamlit run app.py
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `streamlit: command not found` | venv not activated | `source .venv/bin/activate` |
| `ModuleNotFoundError: No module named 'streamlit'` | deps not installed | `pip install -r requirements.txt` |
| Dashboard shows "No analysis data found for X" | outputs/ missing or stale | `./run.sh preprocess` |
| Excel-read error during preprocess | wrong sheet name | dataset must have `Edited` and `Feature_data` sheets — see `../Docs/attribute_schema.md` |
| `command not found: python3.12` | older Python on PATH | install Python 3.12 (see Prerequisites) or set `PYTHON=python3.11 ./run.sh` |
| Streamlit port already in use | another Streamlit running | `./run.sh app -- --server.port 8502` (anything after `--` is passed to streamlit) |

If `pip install` fails on `numpy`/`scikit-learn`, you likely don't have the wheels for your Python version. The pinned set in `requirements.txt` is known to work on Python 3.11 and 3.12 on macOS/Linux.

---

## Adding a new dataset

1. Build a workbook that follows the unified schema in [`../Docs/attribute_schema.md`](../Docs/attribute_schema.md). The template at [`templates/feature_schema_template.xlsx`](templates/feature_schema_template.xlsx) is the easiest starting point — it ships with column-level help comments and dropdown validation for every enum field.
2. Drop it into `Distance-Analysis/` (or any path you can pass to `--excel`).
3. From the venv:
   ```bash
   python preprocessing.py --excel your_file.xlsx
   python compute_distance_matrix.py --excel your_file.xlsx
   mkdir -p outputs/your_dataset
   mv preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/your_dataset/
   ```
4. Wire the new folder into `app.py` (Module 1 in the Exposé will automate this).

---

## Conjoint workflow (customer-weighted distance)

The conjoint pieces (Modules 2–5) are now wired end to end:

- **Module 2 — questionnaire generator** (`conjoint/questionnaire.py`,
  `python -m conjoint.generate_questionnaire`) turns a workbook's `Feature_data`
  sheet into a `questionnaire_spec.json` and an empty `responses.csv` template.
- **Collect ratings** either by filling the template, or via the Streamlit
  multipage **questionnaire** view (`pages/questionnaire.py`): it renders the
  Part B-1 levels as 1..5 inputs and downloads a contract-compliant
  `responses.csv`.
- **Module 3 — estimation** (`python -m conjoint.estimate --responses
  responses.csv --out-utilities utilities.csv --out-importance importance.csv`)
  runs OLS and aggregates per-attribute importance.
- **Module 4 — weighted distance** (`compute_distance_matrix.py --mode weighted
  --importance importance.csv --attribute-map attribute_column_map.json`)
  re-scales each attribute by its relative importance.
- **Module 5 — comparative dashboard** (`app.py`) exposes a
  **Technical | Customer-weighted** toggle.

The quickest way to see it: `./run.sh conjoint` builds an authentic bundled demo
(weighted by the real published N=381 tractor study) into
`outputs/conjoint_demo/`, then writes
`validation/validation_report_conjoint.md`. See
[`../Docs/Expose_v3.md`](../Docs/Expose_v3.md) §6 for the full timeline and
[`../Docs/algorithm_spec.md`](../Docs/algorithm_spec.md) §6/§8 for the weighted
distance math.
