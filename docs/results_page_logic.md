# Results page logic: from data to every chart

This document explains the full logic of the **results page (Conjoint Results)**, from local
questionnaires to every chart, serving as the bridge between the code and how the business
reads it. It is downstream of [`questionnaire_logic.md`](./questionnaire_logic.md): the answers
collected by the questionnaire are fitted here into a preference structure and visualized.

Entry point and launch:

```bash
SURVEY_SPEC=questionnaire_spec_computers.json \
SURVEY_WORKBOOK=computer_survey_questions.xlsx \
  python -m streamlit run results_app.py
```

Code involved:

| Layer | File | Responsibility |
|----|------|------|
| Entry | `results_app.py` | Streamlit entry point, calls a single render function |
| Rendering | `dashboard/results_dashboard.py` | Sidebar + drawing of the 7 panels (`st` injected, testable) |
| Analysis core | `dashboard/results_analysis.py` | Pure computation: two models + five stage-by-stage statistics |
| Modeling engine | `conjoint/acbc/estimate.py` | MNL and HB fitting |
| Simulation engine | `conjoint/acbc/simulation.py` | Share of preference and removal analysis |
| Reading | `conjoint/acbc/responses.py` | Merges local `responses_*.csv` questionnaires |

---

## 1. Overall data flow

```
outputs/survey_responses_<product>/responses_*.csv   (local questionnaires, one file per person)
        │  read_responses_dir()  merges into a long-format table (one file = one respondent)
        ▼
analyze_survey_results(df, ...)        dashboard/results_analysis.py
        │  runs two models + five stage-by-stage statistics
        ▼
SurveyResults  (an immutable frozen dataclass result bundle)
        │
        ▼
render_results_dashboard()  renders the 7 panels    dashboard/results_dashboard.py
```

The input is the merged long table, where each row is `(respondent, stage, task_id, alternative_index, ...)`.
There are 5 kinds of `stage`, and **each panel reads only the stage it needs**:

| stage | Which part of the questionnaire it comes from | Which panel it feeds |
|-------|-------------------|-------------|
| `background` | Part A background | Panel ⑦ Respondent segments |
| `musthave` | B2 veto items (must-have / unacceptable) | Not charted directly (affects profile generation in the questionnaire stage) |
| `tournament` | B4 pairwise choices | Modeling engine (MNL + HB) → Panels ①②③④⑤ |
| `calibration` | B5 purchase likelihood (0–5) | Panel ⑥ Purchase likelihood |
| `wtp` | Part C willingness-to-pay tiers | Panel ④ Willingness-to-pay (left column) |

---

## 2. Sidebar controls (three inputs)

`results_dashboard.py:_load_responses` + `render_results_dashboard`.

| Control | Effect |
|------|------|
| **Data source** | `Local responses folder` (product dropdown, auto-discovers `outputs/survey_responses_*`) or `Upload questionnaires` (upload one or more). After reading, it runs a hard check: **if there are no tournament rows it errors out and exits**, because ACBC estimation depends entirely on the B4 choices. |
| **HB iterations** | 200–4000, the number of HB sampling iterations. 400 is the preview tier (Rhat may be > 1.1); ≥ 4000 is publication grade. |
| **Random seed** | Random seed for HB sampling, ensuring reproducible results. |

The product dropdown is auto-discovered: as soon as `outputs/` contains one more
`survey_responses_<product>` folder, the menu automatically gains one more option
(`_discover_response_dirs`), defaulting to the product matching the current spec.

---

## 3. Underlying modeling engine (two models, using only B4 tournament rows)

`analyze_survey_results` runs two models, and this is the key distinction for understanding the whole page.

### 3.1 MNL (Multinomial Logit, population point estimate)
`estimate.fit_from_responses(df)`

- Takes only the tournament rows, applies **effects coding** to each candidate profile (dropping the
  last level of each attribute as the baseline), maximizes the choice likelihood, and solves for a
  set of coefficients `β`.
- `beta_to_level_utilities(β)` converts `β` back into the **part-worth utility of each level**
  (the whole-sample average taste).
- **Drives: ① importance, ② part-worth, ④ derived WTP.**

### 3.2 HB (Hierarchical Bayes, per-respondent estimate)
`estimate.fit_hb(df, n_iter, seed)`

- Metropolis-within-Gibbs sampling (pure numpy), estimating **each respondent** their own utility
  vector `β_i`, allowing individual heterogeneity.
- Produces `hb_utilities` (one row per person) and `rhat` (the Gelman-Rubin convergence diagnostic).
- **Drives: ① convergence metric, ⑤ market simulator** (the simulator must use individual utilities,
  not the average).

> One-line distinction: **the bar charts (importance, part-worth) come from the MNL population
> average; the simulator and convergence metric come from the HB per-respondent estimate.** The
> caption at the top of the page loosely says "Hierarchical Bayes", but the importance /
> part-worth charts are actually taken from the merged MNL point estimate.

---

## 4. The seven display panels

Each panel is annotated with: **data source / computation logic / display**, along with the
corresponding code function.

### ① Overview & convergence
`_render_overview`

- **Data**: tournament rows + HB's `rhat`.
- **Logic**: `Respondents` = number of unique respondents in tournament; `Tournament tasks` =
  number of `(respondent, task_id)` groups; `Rhat max` = the largest Gelman-Rubin value across all HB
  parameters.
- **Display**: three metrics. `Rhat < 1.1` is judged as "converged", otherwise it warns "preview
  tier, increase iterations".

### ② Attribute importance
`_render_importance` + `estimate.attribute_importance`

- **Data**: MNL part-worths.
- **Logic**: the importance of each attribute = the **range** of that attribute's part-worths (best
  level minus worst level), divided by the sum of all attribute ranges, giving the relative importance
  `Range_A / ΣRange` (summing to 100%). Intuition: the larger the utility spread between an
  attribute's levels, the more it influences the choice.
- **Display**: a horizontal bar chart (ascending), with text calling out the most important attribute.

### ③ Part-worth utilities
`_render_partworths` + `estimate.rescale_zero_centered_diffs`

- **Data**: MNL `level_utilities`, rescaled via `rescale_zero_centered_diffs`.
- **Logic**: converted to a Sawtooth-style **"zero-centered diffs"** scale (mean zeroed within each
  attribute, the table-wide average range rescaled to 100), purely for readability and cross-attribute
  comparison. Higher values are more preferred.
- **Display**: pick an attribute to see the bar chart of its levels; expand to see a table of all attributes.

### ④ Willingness-to-pay (two columns)
`_render_wtp`

**Left column Stated WTP (from Part C actual answers)**, `summarize_wtp`:

- For each upgrade feature, count how many respondents fall into each price band, yielding: the modal
  band, `share_paid` (the proportion who chose "higher than the cheapest band"), and mean / median
  computed by parsing the `$` figures out of the band labels.
- Display: a summary table + a band distribution chart for the selected feature.

**Right column Derived WTP (back-solved from price utilities)**, `derived_monetary_wtp`:

- First compute **how much money each unit of utility is worth**: `usd_per_util = |Δ$| / |Δutility|`
  (using the midpoint of the price-band label interval as the dollar value, taking the slope across
  price levels).
- Then value every other level: `(that level's utility − that attribute's worst-level utility) × usd_per_util`.
- If price is missing / the `$` cannot be parsed from the label / the price utility is flat, it gracefully
  degrades to a notice instead of erroring out.

### ⑤ Market simulator
`_render_simulator` + `conjoint/acbc/simulation.py`

- **Data**: HB's per-respondent utilities `hb_utilities`.
- **Logic**: you configure 2–4 products (pick a level per attribute). For **each respondent** it
  computes each product's total utility = the sum of its level part-worths, then softmax, giving that
  person's `share_of_preference` (logit choice probability); `aggregate_shares` averages over all
  people, i.e. the share of preference.
- **Removal analysis**: `removal_impact` computes the shares before and after removing a product, to
  see where the share transfers.
- **Display**: a share bar chart + a "before / after / change" table after removal.

### ⑥ Purchase likelihood (B5)
`_render_calibration` + `summarize_calibration`

- **Data**: the 0–5 ratings of the calibration rows.
- **Logic**: `mean_probability_pct = mean / 5 × 100`; count the number of people at each 0–5 score; and
  compute each person's mean.
- **Display**: an average purchase likelihood metric + a 0–5 distribution chart.

### ⑦ Respondent segments (Part A)
`_render_segments` + `summarize_background`

- **Data**: the actual answers of the background rows.
- **Logic**: group by question and count the occurrences of each answer (multi-select answers are split
  on `;` and counted separately).
- **Display**: pick a background question to see a horizontal bar chart of its answer distribution.

---

## 5. Graceful degradation design

The whole page gracefully degrades when a stage is missing:

| Missing | Behavior |
|------|------|
| No Part C | WTP left column shows a notice |
| No B5 | Purchase likelihood panel shows a notice |
| No Part A | Respondent segments panel shows a notice |
| Price `$` cannot be parsed | Derived WTP shows a notice |
| **No tournament (B4) rows** | **The whole page errors out and exits** (the only hard requirement, no B4 means no ACBC estimation) |

In addition, if fitting throws an exception, `render_results_dashboard` catches it with try/except and
displays `Analysis failed: ...` instead of letting the whole page crash.

---

## 6. Quick reference: stage → panel → model

| Panel | Stage read | Model / statistic used |
|------|-----------|----------------|
| ① Overview | tournament | HB (Rhat) |
| ② Attribute importance | tournament | MNL range share |
| ③ part-worth | tournament | MNL + rescale |
| ④ Willingness-to-pay (left) | wtp | Band counts |
| ④ Willingness-to-pay (right) | tournament | MNL price-slope back-solve |
| ⑤ Market simulator | tournament | HB per-respondent + logit share |
| ⑥ Purchase likelihood | calibration | 0–5 mean / distribution |
| ⑦ Respondent segments | background | Answer counts |
