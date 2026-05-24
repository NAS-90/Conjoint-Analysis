#!/usr/bin/env bash
# Distance-Analysis bootstrap + launcher.
#
# Usage:
#   ./run.sh                # create venv, install deps, regenerate outputs, launch dashboard
#   ./run.sh setup          # only create venv + install deps
#   ./run.sh preprocess     # only regenerate the three datasets' outputs/
#   ./run.sh app            # only launch streamlit (assumes venv + outputs/ exist)
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
        --validation-report validation/preprocess_tractors.md
    python compute_distance_matrix.py
    mv -f preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/tractors/
    ok "tractors regenerated"

    step "Smartphones → outputs/smartphones/"
    python preprocessing.py \
        --excel "smart phone dataset.xlsx" \
        --validation-report validation/preprocess_smartphones.md
    python compute_distance_matrix.py --excel "smart phone dataset.xlsx" --product-col model
    mv -f preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/smartphones/
    ok "smartphones regenerated"

    if [ -f templates/custom_product_template.xlsx ]; then
        step "User-upload sample → outputs/user_upload/"
        python preprocessing.py \
            --excel templates/custom_product_template.xlsx \
            --validation-report validation/preprocess_user_upload.md
        python compute_distance_matrix.py --excel templates/custom_product_template.xlsx --product-col product
        mv -f preprocessed_output.csv distance_matrix.csv nearest_neighbors.csv distance_summary.txt outputs/user_upload/
        ok "user-upload sample regenerated"
    else
        warn "templates/custom_product_template.xlsx missing — skipping user_upload"
    fi
}

app() {
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    step "Launching Streamlit dashboard"
    python -m streamlit run app.py
}

case "${1:-all}" in
    setup)      setup ;;
    preprocess) preprocess ;;
    app)        app ;;
    all)        setup; preprocess; app ;;
    *)          echo "Usage: $0 [setup|preprocess|app|all]"; exit 2 ;;
esac
