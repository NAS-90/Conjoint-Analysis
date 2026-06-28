# Documentation index

Design and reference docs for Distance-Analysis. Start with the
[project README](../README.md) for the overview and quickstart, then dive in here.

| Doc | Read it when you want to |
|-----|--------------------------|
| [`architecture.md`](./architecture.md) | See the whole system at a glance: runtime surfaces, end-to-end data flow, what each package does, and the file contracts between modules. |
| [`questionnaire_logic.md`](./questionnaire_logic.md) | Understand the survey app (`survey.py`): every Part A / B / C stage, how it maps to the reference design, and the session-state data flow. |
| [`results_page_logic.md`](./results_page_logic.md) | Understand the results dashboard (`results_app.py`): how each of the seven panels is computed and which model (MNL vs Hierarchical Bayes) drives each chart. |
| [`acbc_design_spec.md`](./acbc_design_spec.md) | Understand the ACBC algorithm: effects coding, level balance, the MNL log-likelihood, the HB Gibbs sampler, share-of-preference, and removal impact. |

## Related docs outside this folder

| Doc | Covers |
|-----|--------|
| [`../SETUP.md`](../SETUP.md) | Install, one-command bootstrap, troubleshooting, adding a dataset. |
| [`../../Docs/attribute_schema.md`](../../Docs/attribute_schema.md) | The `Feature_data` workbook schema: columns, validation rules, worked examples. |
| [`../../Docs/algorithm_spec.md`](../../Docs/algorithm_spec.md) | The conjoint math: OLS estimation, aggregation, and the weighted-distance formula. |
| [`../../Docs/Expose_v3.md`](../../Docs/Expose_v3.md) | Project background, the five-module plan, timeline, and team roles. |
