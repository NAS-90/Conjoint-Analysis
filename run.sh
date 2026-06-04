#!/usr/bin/env bash
# Distance-Analysis bootstrap + launcher.
#
# Usage:
#   ./run.sh                # create venv, install deps, regenerate outputs, launch dashboard
#   ./run.sh setup          # only create venv + install deps
#   ./run.sh preprocess     # regenerate the datasets' outputs/ (incl. attribute maps)
#   ./run.sh conjoint       # build the conjoint demo + customer-weighted distances
#   ./run.sh app            # only launch the analysis dashboard (assumes venv + outputs/)
#   ./run.sh survey         # launch the standalone conjoint questionnaire app
#
# Tested on macOS and Linux. On Windows, use WSL or run the equivalent
# commands manually from PowerShell.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
VENV=".venv"

step() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }
ok()   { printf "    \033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "    \033[1;33m!\033[0m %s\n" "$*"; }

setup() {
    step "Python interpreter"
    "$PY" -V

    if [ ! -d "$VENV" ]; then
        step "Creating virtualenv at $VENV"
        "$PY" -m venv "$VENV"
    fi

    # shellcheck disable=SC1091
    source "$VENV/bin/activate"

    step "Installing pinned dependencies (requirements.txt)"
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    ok "dependencies installed: $(python -m pip freeze | wc -l | tr -d ' ') packages"
}

preprocess() {
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"

    mkdir -p outputs/tractors outputs/smartphones outputs/user_upload

    step "Tractors → outputs/tractors/"
    python preprocessing.py \
        --excel "Database_Distance Analysis.xlsx" \
        --validation-report validation/preprocess_tractors.md \
        --attribute-map outputs/tractors/attribute_column_map.json
    python compute_distance_matrix.py
    mv -f preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/tractors/
    ok "tractors regenerated"

    step "Smartphones → outputs/smartphones/"
    # Clean noisy composite strings (camera "50 MP + 8 MP + 2 MP …", display
    # "6.7 inches, 1440 x 3216 px, 120 Hz …") and realign column-shifted
    # feature-phone rows before the universal preprocessor runs.
    python clean_smartphones.py \
        --input "smart phone dataset.xlsx" \
        --output "smart phone dataset (cleaned).xlsx"
    python preprocessing.py \
        --excel "smart phone dataset (cleaned).xlsx" \
        --validation-report validation/preprocess_smartphones.md \
        --attribute-map outputs/smartphones/attribute_column_map.json
    python compute_distance_matrix.py --excel "smart phone dataset (cleaned).xlsx" --product-col model
    mv -f preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/smartphones/
    ok "smartphones regenerated"

    if [ -f templates/custom_product_template.xlsx ]; then
        step "User-upload sample → outputs/user_upload/"
        python preprocessing.py \
            --excel templates/custom_product_template.xlsx \
            --validation-report validation/preprocess_user_upload.md \
            --attribute-map outputs/user_upload/attribute_column_map.json
        python compute_distance_matrix.py --excel templates/custom_product_template.xlsx --product-col product
        mv -f preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/user_upload/
        ok "user-upload sample regenerated"
    else
        warn "templates/custom_product_template.xlsx missing — skipping user_upload"
    fi
}

# Is an attribute_column_map.json present and non-empty (i.e. "{}" plus a few
# braces is treated as empty)? Used to decide whether a dataset carries conjoint
# attributes that the customer-weighted distance can consume.
attribute_map_nonempty() {
    local map="$1"
    [ -f "$map" ] || return 1
    python - "$map" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(data, dict) and len(data) > 0 else 1)
PY
}

# Compute the customer-weighted distance for one already-preprocessed dataset.
#   $1 dataset folder under outputs/   $2 workbook   $3 product-col
weighted_for_dataset() {
    local ds="$1" excel="$2" product_col="$3"
    local out="outputs/$ds"
    local pre="$out/preprocessed_output.csv"
    local map="$out/attribute_column_map.json"
    local imp="$out/importance.csv"
    local resp="$out/responses.csv"

    if [ ! -f "$pre" ] || ! attribute_map_nonempty "$map"; then
        warn "$ds: no preprocessed matrix or empty attribute map — skipping weighted distance"
        return 0
    fi

    # If a survey exists but importance has not been estimated yet, estimate it.
    # We prefer the ACBC long-format file (acbc_responses.csv) when present
    # — it triggers the MNL path; otherwise fall back to OLS on responses.csv.
    local acbc_resp="$out/acbc_responses.csv"
    if [ ! -f "$imp" ] && [ -f "$acbc_resp" ]; then
        step "$ds: estimating importance from acbc_responses.csv (MNL)"
        python -m conjoint.acbc.estimate \
            --responses "$acbc_resp" --out-importance "$imp"
    elif [ ! -f "$imp" ] && [ -f "$resp" ]; then
        step "$ds: estimating importance from responses.csv (OLS)"
        python -m conjoint.estimate --responses "$resp" --out-importance "$imp"
    fi

    if [ ! -f "$imp" ]; then
        warn "$ds: no importance.csv (and no responses/acbc_responses.csv) — skipping weighted distance"
        return 0
    fi

    step "$ds: customer-weighted distance → $out/"
    python compute_distance_matrix.py \
        --excel "$excel" --product-col "$product_col" \
        --input-csv "$pre" \
        --mode weighted --importance "$imp" --attribute-map "$map"
    mv -f distance_matrix_weighted.csv nearest_neighbors_weighted.csv "$out/"
    ok "$ds weighted distance regenerated"
}

conjoint() {
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"

    mkdir -p outputs/conjoint_demo

    step "Building conjoint demo workbook (conjoint_demo.xlsx)"
    python scripts/build_demo_workbook.py --out conjoint_demo.xlsx
    ok "demo workbook built"

    step "Conjoint demo → outputs/conjoint_demo/"
    python preprocessing.py \
        --excel conjoint_demo.xlsx \
        --output outputs/conjoint_demo/preprocessed_output.csv \
        --attribute-map outputs/conjoint_demo/attribute_column_map.json \
        --validation-report validation/preprocess_conjoint_demo.md
    # Customer importance is the *real* published N=381 study, not fabricated.
    python scripts/build_demo_importance.py --out outputs/conjoint_demo/importance.csv
    # Technical (unweighted) distance for the same configs.
    python compute_distance_matrix.py \
        --excel conjoint_demo.xlsx --product-col product_id \
        --input-csv outputs/conjoint_demo/preprocessed_output.csv
    mv -f distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/conjoint_demo/
    weighted_for_dataset conjoint_demo conjoint_demo.xlsx product_id
    ok "conjoint demo regenerated"

    # Opportunistically add a customer-weighted view to any existing dataset that
    # already carries conjoint attributes (non-empty attribute map) and an
    # importance.csv (or a responses.csv we can estimate from).
    weighted_for_dataset tractors "Database_Distance Analysis.xlsx" model
    weighted_for_dataset smartphones "smart phone dataset (cleaned).xlsx" model
    if [ -f templates/custom_product_template.xlsx ]; then
        weighted_for_dataset user_upload templates/custom_product_template.xlsx product
    fi

    step "Conjoint validation report"
    python validation/validate_conjoint.py \
        --dataset-dir outputs/conjoint_demo \
        --out validation/validation_report_conjoint.md
    ok "validation/validation_report_conjoint.md regenerated"
}

app() {
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    step "Launching Streamlit dashboard"
    python -m streamlit run app.py
}

survey() {
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    if [ ! -f questionnaire_spec.json ]; then
        warn "questionnaire_spec.json missing — generating it from conjoint_demo.xlsx"
        python -m conjoint.generate_questionnaire \
            --excel conjoint_demo.xlsx --out questionnaire_spec.json
    fi
    step "Launching standalone conjoint survey app"
    python -m streamlit run survey.py
}

case "${1:-all}" in
    setup)      setup ;;
    preprocess) preprocess ;;
    conjoint)   conjoint ;;
    app)        app ;;
    survey)     survey ;;
    all)        setup; preprocess; conjoint; app ;;
    *)          echo "Usage: $0 [setup|preprocess|conjoint|app|survey|all]"; exit 2 ;;
esac
