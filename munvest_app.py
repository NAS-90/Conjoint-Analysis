"""Streamlit Cloud entry point: builds the demo outputs on first start, then runs the dashboard."""
import os, subprocess, sys, runpy
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
PY = sys.executable
def run(*a):
    subprocess.run([PY, *a], check=True, cwd=ROOT)
def mv(files, dest):
    os.makedirs(dest, exist_ok=True)
    for f in files:
        if os.path.exists(f):
            os.replace(f, os.path.join(dest, f))
def build():
    os.makedirs("outputs/tractors", exist_ok=True)
    run("preprocessing.py", "--excel", "Database_Distance Analysis.xlsx", "--validation-report", "validation/preprocess_tractors.md", "--attribute-map", "outputs/tractors/attribute_column_map.json")
    run("compute_distance_matrix.py")
    mv(["preprocessed_output.csv", "distance_matrix.csv", "nearest_neighbors.csv", "distance_summary.txt"], "outputs/tractors")
    os.makedirs("outputs/smartphones", exist_ok=True)
    run("clean_smartphones.py", "--input", "smart phone dataset.xlsx", "--output", "smart phone dataset (cleaned).xlsx")
    run("preprocessing.py", "--excel", "smart phone dataset (cleaned).xlsx", "--validation-report", "validation/preprocess_smartphones.md", "--attribute-map", "outputs/smartphones/attribute_column_map.json")
    run("compute_distance_matrix.py", "--excel", "smart phone dataset (cleaned).xlsx", "--product-col", "model")
    mv(["preprocessed_output.csv", "distance_matrix.csv", "nearest_neighbors.csv", "distance_summary.txt"], "outputs/smartphones")
    os.makedirs("outputs/conjoint_demo", exist_ok=True)
    run("scripts/build_demo_workbook.py", "--out", "conjoint_demo.xlsx")
    run("preprocessing.py", "--excel", "conjoint_demo.xlsx", "--output", "outputs/conjoint_demo/preprocessed_output.csv", "--attribute-map", "outputs/conjoint_demo/attribute_column_map.json", "--validation-report", "validation/preprocess_conjoint_demo.md")
    run("scripts/build_demo_importance.py", "--out", "outputs/conjoint_demo/importance.csv")
    run("compute_distance_matrix.py", "--excel", "conjoint_demo.xlsx", "--product-col", "product_id", "--input-csv", "outputs/conjoint_demo/preprocessed_output.csv")
    mv(["distance_matrix.csv", "nearest_neighbors.csv", "distance_summary.txt"], "outputs/conjoint_demo")
    run("compute_distance_matrix.py", "--excel", "conjoint_demo.xlsx", "--product-col", "product_id", "--input-csv", "outputs/conjoint_demo/preprocessed_output.csv", "--mode", "weighted", "--importance", "outputs/conjoint_demo/importance.csv", "--attribute-map", "outputs/conjoint_demo/attribute_column_map.json")
    mv(["distance_matrix_weighted.csv", "nearest_neighbors_weighted.csv"], "outputs/conjoint_demo")
if not os.path.exists("outputs/conjoint_demo/distance_matrix_weighted.csv"):
    import streamlit as st
    with st.spinner("First start: preparing demo data (about 1 minute)..."):
        build()
runpy.run_path(os.path.join(ROOT, "app.py"), run_name="__main__")
