"""Data preparation for the Munvest demo apps (builds demo outputs on first start)."""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(*a, env=None):
    subprocess.run([PY, *a], check=True, cwd=ROOT, env={**os.environ, **(env or {})})

def mvf(files, dest):
    os.makedirs(dest, exist_ok=True)
    for f in files:
        if os.path.exists(f):
            os.replace(f, os.path.join(dest, f))

def build():
    os.makedirs("outputs/tractors", exist_ok=True)
    run("preprocessing.py", "--excel", "Database_Distance Analysis.xlsx", "--validation-report", "validation/preprocess_tractors.md", "--attribute-map", "outputs/tractors/attribute_column_map.json")
    run("compute_distance_matrix.py")
    mvf(["preprocessed_output.csv", "distance_matrix.csv", "nearest_neighbors.csv", "distance_summary.txt"], "outputs/tractors")
    os.makedirs("outputs/smartphones", exist_ok=True)
    run("clean_smartphones.py", "--input", "smart phone dataset.xlsx", "--output", "smart phone dataset (cleaned).xlsx")
    run("preprocessing.py", "--excel", "smart phone dataset (cleaned).xlsx", "--validation-report", "validation/preprocess_smartphones.md", "--attribute-map", "outputs/smartphones/attribute_column_map.json")
    run("compute_distance_matrix.py", "--excel", "smart phone dataset (cleaned).xlsx", "--product-col", "model")
    mvf(["preprocessed_output.csv", "distance_matrix.csv", "nearest_neighbors.csv", "distance_summary.txt"], "outputs/smartphones")
    os.makedirs("outputs/conjoint_demo", exist_ok=True)
    run("scripts/build_demo_workbook.py", "--out", "conjoint_demo.xlsx")
    run("preprocessing.py", "--excel", "conjoint_demo.xlsx", "--output", "outputs/conjoint_demo/preprocessed_output.csv", "--attribute-map", "outputs/conjoint_demo/attribute_column_map.json", "--validation-report", "validation/preprocess_conjoint_demo.md")
    run("scripts/build_demo_importance.py", "--out", "outputs/conjoint_demo/importance.csv")
    run("compute_distance_matrix.py", "--excel", "conjoint_demo.xlsx", "--product-col", "product_id", "--input-csv", "outputs/conjoint_demo/preprocessed_output.csv")
    mvf(["distance_matrix.csv", "nearest_neighbors.csv", "distance_summary.txt"], "outputs/conjoint_demo")
    run("compute_distance_matrix.py", "--excel", "conjoint_demo.xlsx", "--product-col", "product_id", "--input-csv", "outputs/conjoint_demo/preprocessed_output.csv", "--mode", "weighted", "--importance", "outputs/conjoint_demo/importance.csv", "--attribute-map", "outputs/conjoint_demo/attribute_column_map.json")
    mvf(["distance_matrix_weighted.csv", "nearest_neighbors_weighted.csv"], "outputs/conjoint_demo")

def build_responses():
    run("scripts/make_survey_responses.py", "--n", "50", "--seed", "2026",
        env={"SURVEY_SPEC": "questionnaire_spec_computers.json", "SURVEY_WORKBOOK": "computer_survey_questions.xlsx"})

def ensure(responses=True):
    if not os.path.exists("outputs/conjoint_demo/distance_matrix_weighted.csv"):
        build()
    d = "outputs/survey_responses_computers"
    if responses and not (os.path.isdir(d) and os.listdir(d)):
        build_responses()
