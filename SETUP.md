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
2. **preprocess** — runs the universal `Feature_data`-driven preprocessor for all three datasets and writes outputs to `outputs/{tractors,smartphones,user_upload}/`.
3. **app** — launches `streamlit run app.py`.

You can run each phase independently:

```bash
./run.sh setup        # only create venv + install deps
./run.sh preprocess   # only regenerate outputs/
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

## What's next

This setup is the P1 deliverable ("Get Streamlit running for everyone"). It does **not** yet include the conjoint pieces — those land in P2:

- Module 2 (questionnaire generator) → `Docs/algorithm_spec.md`
- Module 3 (conjoint computation) → `Docs/algorithm_spec.md`
- Module 4 (weighted distance) → extends `compute_distance_matrix.py`
- Module 5 (comparative dashboard) → extends `app.py`

See [`../Docs/Expose_v3.md`](../Docs/Expose_v3.md) §6 for the full timeline.
