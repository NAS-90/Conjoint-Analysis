# Questionnaire logic — design reference → code

This document records how the survey **code** implements the questionnaire
design in the reference doc *"0603 M3 问卷问题&逻辑"* (the Part A / B / C structure
adapted from Nicolas's N=381 tractor study to a product-agnostic prototype).

It is the bridge between *what the reference asks for* and *what the code in
`survey.py` + `survey_views/` actually does*. The app entry point is `survey.py`
(`streamlit run survey.py`, or `./run.sh survey`).

> Analysis goal pipeline (from the reference):
> **问卷回答 → 用户偏好 → attribute importance → customer-weighted distance analysis**

---

## 1. Overall structure

The reference proposes three parts:

| Part | Reference title | Purpose |
|------|-----------------|---------|
| **A** | 用户筛选与背景信息 | Respondent profiling / segmentation |
| **B** | ACBC-like 偏好问题 (B0–B5) | The conjoint core — preferences, constraints, choices |
| **C** | Willingness-to-Pay / Surcharge | Price sensitivity / business value |

The code renders **one linear flow** (no mode gate — everyone takes the same
path) via an `st.navigation` router in `survey.py`:

```
Welcome → Part A → B0 → B2 → B4 → B5 → Part C → Thank you
```

### What is and isn't implemented

The reference lists six B-stages (B0–B5). The prototype implements **B0, B2, B4,
B5** and **intentionally omits B1 and B3**:

| Stage | Reference | Implemented? | Code |
|-------|-----------|:---:|------|
| **Part A** | Introduction / background | ✅ | `survey_views/part_a_background.py` |
| **B0** | Feature Explanation 属性解释 | ✅ | `survey_views/b0_features.py` |
| **B1** | Feature Rating 单属性吸引力评分 | ❌ omitted | — (was `ratings.py`, removed) |
| **B2** | Must-have / Unacceptable 必须/不可接受 | ✅ | `survey_views/b2_constraints.py` |
| **B3** | Importance 属性差异重要性 | ❌ omitted | — |
| **B4** | Pair Comparison / Choice Tasks | ✅ | `survey_views/acbc_tournament.py` |
| **B5** | Calibration 购买概率校准 | ✅ | `survey_views/b5_calibration.py` |
| **Part C** | Surcharge / WTP | ✅ | `survey_views/part_c_wtp.py` |

**Why B1/B3 are dropped.** The reference itself flags B1 as *"不是很重要"* (a
classical evaluation step, not true conjoint) and B3 as an auxiliary
cross-check. The choice data in **B4** is the real driver of part-worth
utilities and importance, so the prototype keeps the flow short and lets B2's
constraints (not B1's ratings) seed the respondent's ideal **anchor**. Anywhere
the code "would have used B1 ratings" it passes an empty ratings dict instead
(see B2/B4/B5 below).

---

## 2. Two data sources (product-agnostic)

The questionnaire is entirely **data-driven**, so switching products (e.g.
smartphone → computer) needs *no code change* — only different data:

| Concern | Source file | Loader | Override |
|---------|-------------|--------|----------|
| **Conjoint attributes** (B0/B2/B4/B5) | `questionnaire_spec.json` | `survey_views/spec_source.py` → `load_spec()` | `?spec=<path>` query param → `SURVEY_SPEC` env → bundled default |
| **Part A / bands / Part C** | `survey_questions.xlsx` (`Survey_questions` sheet) | `survey_views/section_source.py` → `load_background_questions()` / `load_amount_bands()` / `load_wtp_features()` | explicit arg → `SURVEY_WORKBOOK` env → conventional default |

Both loaders are **fail-soft**: a missing/invalid source logs a warning and
falls back to the built-in smartphone defaults, so the respondent app never
crashes. The conjoint spec is generated from a workbook's `Feature_data` sheet
via `python -m conjoint.generate_questionnaire`.

---

## 3. The sequential page controller

Every multi-question stage (Part A, B2, B4, B5, Part C) runs on one shared
controller, `survey_views/navigation.py`:

- A stage declares a tuple of `Step`s (`identifier`, `title`, `render`).
- `render_sequence(stage, steps, on_complete=…)` shows **one step per screen**
  with a progress bar and Back / Next (or Finish) chrome.
- A step's `render()` returns `True` when its answer is complete, which enables
  **Next**. Answers are stored per-stage under `STAGE_ANSWERS_KEY` via
  `record_answer(stage, id, value)` and read back with `get_answer(...)`.
- On the last step, **Finish** calls the stage's `on_complete()`, which persists
  any derived state and `advance_to(<next page>)` (`st.switch_page`).

Each stage owns an isolated answer dict (keyed by stage name) so re-entering a
section never bleeds data across stages.

---

## 4. Stage-by-stage logic

### Welcome — `survey_views/intro.py`
Landing page: title, "what to expect" summary, and an **optional** respondent
id/name captured into `RESPONDENT_KEY`. **Start →** opens Part A. No mode
chooser (single linear flow).

### Part A — 用户筛选与背景信息 — `part_a_background.py`  (stage `background`)
- **Reference:** Introduction Questions — purchase intent, current device,
  budget, usage, top factor (tractor → phone/computer scenario).
- **Code:** loads the `section=A` questions from the workbook
  (`load_background_questions()`); renders one per screen as a `radio` (single)
  or `multiselect` (multi). Each answer is recorded under stage `background`.
- **Role:** respondent profiling / segmentation only — these answers do **not**
  enter utility estimation; they are written verbatim into the output CSV.
- **Finish →** B0.

### B0 — Feature Explanation 属性解释 — `b0_features.py`
- **Reference:** explain every attribute and its levels *before* preference
  questions, so technical terms don't corrupt later choice data.
- **Code:** purely informational, **no answers recorded**. Built entirely from
  the loaded `QuestionnaireSpec` (`load_spec()`), so it always matches the
  active attributes — for each active attribute it prints the display name,
  description and its level labels.
- **"I'm ready" →** B2.

### B2 — Must-have / Unacceptable 必须/不可接受 — `b2_constraints.py`  (stage `musthave`)
- **Reference:** ACBC screening logic — learn hard constraints first so only
  realistic concepts are ever shown.
- **Code:** one attribute per screen. Per attribute the respondent may pick an
  optional **must-have** level (`selectbox`) and any **never-accept** levels
  (`multiselect`); both are optional, so the page is always "complete".
- **On Finish** (`_persist_constraints_and_anchor`):
  1. fold per-level answers into `must_have` / `unacceptable` maps via
     `conjoint.acbc.constraints.split_constraints` → stored in `MUST_HAVE_KEY` /
     `UNACCEPTABLE_KEY`;
  2. derive the respondent's **ideal anchor** with
     `anchor_from_ratings({}, spec, must_have, unacceptable)` — *empty ratings*
     (no B1), so the anchor is the spec's level order with must-haves overriding
     per attribute → stored in `ACBC_ANCHOR_KEY`;
  3. `advance_to` B4.

### B4 — Pair Comparison / Choice Tasks — `acbc_tournament.py`  (stage `acbc_tournament`)
- **Reference:** the *core* of the conjoint — show two complete concepts, ask
  for a simulated purchase choice; this choice data drives part-worth utilities,
  importance and customer weights.
- **Code (pool → tasks → choices):**
  - **Pool** (`_resolve_pool`): centred on the B2 anchor — near-anchor
    perturbations (`seed_screener_pool`) plus a balanced design
    (`generate_profiles`), kept only if they satisfy the B2 constraints
    (`filter_by_constraints`); a safety net tops up with unfiltered profiles so a
    pair can always be shown.
  - **Tasks** (`build_tasks`): defaults **8 tasks × 2 alternatives** per task,
    seed `2026`, target pool `16` (design knobs are fixed so respondents never
    see them).
  - **Per screen:** two bordered "Option A / B" cards (attribute → level lines);
    a `radio` records the chosen index under stage `acbc_tournament`.
- **On Finish:** assemble a long-format choice frame
  (`acbc_responses.assemble_tournament_responses`), validate it, and publish it
  to the summary bucket (`acbc_summary_frames`); `advance_to` B5.

### B5 — Calibration 购买概率校准 — `b5_calibration.py`  (stage `calibration`)
- **Reference:** pair comparison tells us *which* of two, not *whether* they'd
  buy. Calibration fills that gap: 0–5 purchase probability
  (0 = definitely not, 5 = definitely).
- **Code:** shows the anchor plus up to two distinct, constraint-valid
  near-anchor variants (`calibration_concepts`, default 3 concepts, seed
  `2026`); each concept gets a 0–5 `radio`. The concept list is stashed in
  `CALIBRATION_CONCEPTS_KEY` so the summary can pair each answer with its
  profile. Answers recorded under stage `calibration`.
- **Finish →** Part C.

### Part C — Willingness-to-Pay / Surcharge — `part_c_wtp.py`  (stage `wtp`)
- **Reference:** would the respondent pay *extra* for specific upgrades? A
  lightweight, ACBC-flavoured section that informs price sensitivity / business
  value (not core utility estimation).
- **Code:** one upgrade per screen; each answered by an **amount band** `radio`.
  Both the upgrade list (`section=C`) and the amount bands (`section=bands`) are
  product-driven from the workbook (`load_wtp_features()` /
  `load_amount_bands()`). Answers recorded under stage `wtp`.
- **Finish →** Thank you.

### Thank you — `acbc_summary.py`
- Hides all analysis detail; shows a confirmation, an optional "Your ideal
  configuration" recap (the anchor), and a single **Send my responses** button.
- `_combined_frame` merges every completed section — Part A `background`, B2
  `musthave`, B4 tournament frames (from the bucket), B5 `calibration`, Part C
  `wtp` — into one **long-format** CSV via `conjoint.acbc.responses`
  (`assemble_*_responses` + `concat_responses`), downloaded as
  `responses_<respondent>.csv`.

---

## 5. Session-state data flow

```
Welcome   RESPONDENT_KEY ─────────────────────────────────────────────┐
Part A    STAGE_ANSWERS_KEY["background"] ──────────────────────────┐  │
B0        (no state — informational)                                │  │
B2        MUST_HAVE_KEY, UNACCEPTABLE_KEY ──► ACBC_ANCHOR_KEY ──┐    │  │
B4        anchor+constraints ► pool ► tasks ► acbc_summary_frames│   │  │
B5        anchor+constraints ► CALIBRATION_CONCEPTS_KEY + answers│   │  │
Part C    STAGE_ANSWERS_KEY["wtp"] ─────────────────────────────┤   │  │
                                                                ▼   ▼  ▼
Thank you   _combined_frame() ──►  one long-format responses_<id>.csv
```

Keys are defined in `survey_views/state.py`. The navigation controller owns
`STAGE_KEY` / `STEP_INDEX_KEY` / `STAGE_ANSWERS_KEY`; each `*_PAGE_KEY` stashes
an `st.Page` handle so a stage's Finish can `switch_page` to the next.

---

## 6. Supporting conjoint modules (`conjoint/acbc/`)

| Module | Used by | Provides |
|--------|---------|----------|
| `constraints.py` | B2, B4, B5 | `split_constraints`, `anchor_from_ratings`, `filter_by_constraints` |
| `design.py` | B4, B5, summary | `Profile`, `attribute_levels_from_spec`, `generate_profiles` |
| `screener.py` | B4, B5 | `seed_screener_pool` (near-anchor perturbations) |
| `tournament.py` | B4 | `Task`, `build_tasks` (pair/choice task design) |
| `responses.py` | B4, summary | `assemble_*_responses`, `validate_acbc_responses`, `concat_responses` |

Downstream, the merged `responses.csv` feeds `python -m conjoint.acbc.estimate`
(MNL + optional Hierarchical-Bayes) → attribute importance →
customer-weighted distance analysis, closing the reference's pipeline.
