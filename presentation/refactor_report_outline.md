# Presentation outline · From Distance Analysis to Conjoint Analysis

> This outline is for the `refactor_report.html` slides.  
> After re-reading `../Docs/Expose_v3.md`, I reworked the main storyline into the following logic:
>
> **The current tool is Distance Analysis.**  
> It computes how similar products are to each other based on their technical specifications.
>
> **The project's final goal is not just plain distance analysis, but adding Conjoint Analysis.**  
> In other words: first collect customer preferences through a survey, then turn how much customers value each attribute into weights, and finally make the distance matrix reflect "similarity as customers see it."
>
> So this P1 presentation needs to make clear:  
> what I am building now is not the final conjoint module, but a foundation that turns the existing distance analysis tool into something the later conjoint modules can plug into.

---

## Part 1: First, clarify the project direction (pages 1-3)

### 1. Cover: *From Distance Analysis to Conjoint Analysis*

**What this slide should convey:**  
This presentation is not just about code refactoring, but about how the first phase lays the foundation for the final conjoint analysis tool.

**How to present it:**  
The tool we have today is called Distance Analysis. It can compute, from product specifications, which products are similar and which are very different.  
But the final goal in the Exposé goes one step further: bring customer preferences into the picture, so the tool looks not only at technical specifications but also at what customers truly care about.

**Key takeaway:**  
The current phase is the first step from distance analysis toward conjoint analysis.

---

### 2. The current tool and the final goal: *Technical distance today, customer-weighted distance next*

**What this slide should convey:**  
The difference between the current tool and the final goal.

**How to present it:**  
Today's distance analysis mainly answers this question:

> Based on product specifications, which products are similar to each other?

But the final conjoint-based tool needs to answer:

> Based on customer preferences, which products are really similar to each other?

These two answers may differ.  
Two products can be very close in technical specifications, but if the attributes customers care about most are different, they may not be similar in customers' eyes.

**Suggested on-screen content:**

| Current version | Target version |
|---|---|
| Technical Distance Analysis | Conjoint-weighted Distance Analysis |
| All attributes treated as roughly equally important | Attribute importance comes from a customer survey |
| Looks at engineering specifications | Looks at customer preferences + engineering specifications |
| Outputs a plain distance matrix | Outputs a technical vs customer-weighted comparison |

**Relation to the Exposé:**  
Corresponds to Sections 1-3 of the Exposé: the existing tool can compute technical distance, but lacks the customer perspective.

---

### 3. Why we need Conjoint: *Not every feature matters equally*

**What this slide should convey:**  
The core problem pointed out in the Exposé: today's distance analysis assumes every attribute is equally important.

**How to present it:**  
The current distance computation standardizes all features, then includes them with essentially equal importance.  
This works technically, but it does not necessarily match how customers actually decide.

For example:  
if a customer cares a lot about transmission but not much about tank size, then these two attributes should not have the same influence in the distance computation.

**Key sentence:**  
The role of conjoint analysis is to turn "what customers consider important" into numerical weights.

**Example:**  
Today's technical distance might treat `transmission_type`, `tank_capacity`, and `wheelbase` all as ordinary attributes contributing to the distance computation.  
But if the survey results show that customers care most about `transmission_type` and not much about `wheelbase`, then the later conjoint-weighted distance will let differences in transmission count for more and differences in wheelbase count for less.

**Key takeaway:**  
Conjoint is not another standalone display feature, but the core input that will, in turn, change the distance calculation later.

---

## Part 2: Why P1 fixes the foundation first (pages 4-6)

### 4. The later modules need a stable data entry point: *Conjoint needs clean metadata*

**What this slide should convey:**  
To automatically generate the survey, compute conjoint, and then weight the distance, the prerequisite is that the data structure must be unified.

**How to present it:**  
The Exposé breaks the later work into five modules:

1. Universal Preprocessor;
2. Questionnaire Generator;
3. Conjoint Computation;
4. Weighted Distance;
5. Comparative Dashboard.

These modules do not each work on their own.  
Module 2 reads product attributes to generate the survey, Module 3 needs to know which levels each attribute has, and Module 4 maps the conjoint weights back onto the distance matrix.  
So if the data schema at the very front is not stable, all the later conjoint modules will fail to connect.

**Key takeaway:**  
The P1 refactor is not about "making the code look nice," but about giving the later conjoint pipeline a unified entry point.

---

### 5. Problem one: data-cleaning logic was inconsistent: *The same preprocessing was repeated*

**What this slide should convey:**  
The old tool could run distance analysis, but it was not an architecture suited for extending to conjoint.

**How to present it:**  
Originally, different datasets had different preprocessing scripts.  
They all did similar things: clean the table, transform the data, prepare the distance matrix.  
This is fine for a demo, but very risky for the five modules that follow.

**Why it affects conjoint:**  
If tractor, smartphone, and user-upload data are each cleaned with different rules, then when later automatically generating the survey and computing weights, it is hard to guarantee they read the same data structure.

**To understand it through a small distance analysis example:**

Distance analysis cannot compute directly on raw Excel.  
What it ultimately needs is an "all-numeric" product table, because the distance computation is essentially comparing how close two rows of numbers are.

Take the tractor data as an example. The raw `Edited` sheet might look like this:

| product | hp_range | transmission_type | tank_capacity |
|---|---:|---|---:|
| MF Essential II | `61-70` | `Synchronized` | 85 |
| MF Standard II | `61-70` | `Not Synchronized` | 85 |
| MF Premium | `71-80` | `Powershift` | 105 |

But this table cannot be used to compute distance directly, because it contains ranges, text categories, and different types of fields.  
So the program also reads the `Feature_data` description sheet:

| feature_name | data_types | normalization_method | ideal_direction |
|---|---|---|---|
| hp_range | ordinal | ordinal-mapping | higher |
| transmission_type | nominal | none | neutral |
| tank_capacity | metric | z-score | higher |

After preprocessing, the program turns it into a numeric table that distance analysis can use:

| product | hp_range | transmission_Synchronized | transmission_Not_Synchronized | transmission_Powershift | tank_capacity |
|---|---:|---:|---:|---:|---:|
| MF Essential II | 65.5 | 1 | 0 | 0 | 85 |
| MF Standard II | 65.5 | 0 | 1 | 0 | 85 |
| MF Premium | 75.5 | 0 | 0 | 1 | 105 |

Only then can the distance matrix compare:

|  | Essential II | Standard II | Premium |
|---|---:|---:|---:|
| Essential II | 0 | small distance | a bit larger |
| Standard II | small distance | 0 | a bit larger |
| Premium | a bit larger | a bit larger | 0 |

**Problems without a unified preprocessor:**

- the tractor script has to know on its own that `61-70` should become 65.5;
- the smartphone script has to know on its own that `₹54,999.00` needs its currency symbol and commas stripped;
- if another bicycle dataset comes along, yet another set of bicycle rules has to be written;
- the later conjoint modules would also have to understand each dataset's special format separately.

**What the unified preprocessor now achieves:**

- whether it is tractor, smartphone, or user upload, every field is first described with the same `Feature_data` schema;
- the program decides from the schema whether each column is metric, ordinal, binary, or nominal;
- the program produces a unified `preprocessed_output.csv`;
- both the distance matrix and the later conjoint modules only need to read this unified output.

**Key takeaway:**  
The conjoint modules need a unified data language, and cannot be built on several repeated scripts.

---

### 6. Problem two: it was hard for others to reproduce the workflow: *Hard to run, hard to build on*

**What this slide should convey:**  
P1 also has to solve the problem of "can the rest of the team get it running."

**How to present it:**  
If a teammate wants to continue with Module 2 or Module 3, they should not first have to spend a lot of time guessing:

- which dependencies to install;
- which file to run first;
- where the result files are;
- which output can be handed to the next module.

If the basic workflow is unclear, the later work on the questionnaire, conjoint computation, and weighted distance will all be slowed down.

**Relation to the Exposé:**  
The P1 tasks include run existing tool, get Streamlit running for everyone, and define unified attribute schema.  
These are all prerequisites for the later P2/P3.

**Key takeaway:**  
The value of this P1 is to let the later modules keep building on the same reproducible foundation.

---

## Part 3: What I specifically changed in this P1 (pages 7-10)

### 7. Core idea: *One schema connects distance and conjoint*

**What this slide should convey:**  
The core of the new design is not to serve only distance analysis, but to prepare data for both distance and conjoint at the same time.

**How to present it:**  
Now the user not only uploads product data, but also describes each attribute in `Feature_data`:

- what type this attribute is;
- whether it participates in the analysis;
- how it is standardized;
- whether it is an attribute in conjoint;
- which conjoint levels it has;
- which part of the survey it should appear in.

This way, the same schema can serve both directions at once:  
the front end uses it for the distance matrix, and the back end uses it for the questionnaire generator and conjoint computation.

**Key takeaway:**  
The schema is the bridge between distance analysis and conjoint analysis.

---

### 8. Improvement one: preprocessing becomes the universal Module 1: *A universal preprocessor*

**What this slide should convey:**  
I have already organized the old preprocessing logic into a baseline version of Module 1.

**How to present it:**  
The core cleaning logic is now centralized in `preprocessing.py`.  
Tractor, smartphone, and user-upload data can all be processed through the same universal preprocessor, instead of each maintaining its own set of rules.

**What it prepares for conjoint:**

- reads `Edited` and `Feature_data` in a unified way;
- outputs a computable `preprocessed_output.csv`;
- preserves the attribute metadata the later modules need;
- routes different product categories through the same entry point.

**Comparison of the actual workflow:**

The previous workflow was more like this:

```text
Tractor Excel
  → tractor-specific preprocessing rules
  → tractor numeric table
  → tractor distance matrix

Smartphone Excel
  → smartphone-specific preprocessing rules
  → smartphone numeric table
  → smartphone distance matrix
```

The problem is: although both datasets ultimately enter distance analysis, the upstream cleaning rules are scattered in different places.  
If you later want to build a conjoint questionnaire, this workflow is hard to reuse.

The workflow now becomes:

```text
Any product Excel
  → Edited sheet: raw product data
  → Feature_data sheet: tells the program how to read each column
  → universal preprocessing.py
  → one numeric preprocessed_output.csv
  → distance matrix now
  → questionnaire / conjoint / weighted distance later
```

**Example:**

| Raw data | What the schema tells the program | Unified preprocessing output | How it is used later |
|---|---|---|---|
| Tractor `hp_range = 61-70` | This is ordinal, higher is better | `65.5` | Can enter technical distance; can later serve as a conjoint attribute |
| Tractor `transmission_type = Synchronized` | This is nominal, with multiple levels | `transmission_Synchronized = 1` | Can compare configuration differences; can later generate a transmission survey question |
| Smartphone `price = ₹54,999.00` | This is metric, lower price is better | `54999`, then standardized | Can enter technical distance; can later support price-related analysis |
| Smartphone `os = Android v13` | This is nominal | `os_Android_v13 = 1` | Can compare OS differences; can later decide whether to enter conjoint |

You can state it verbally in one sentence:  
before, "each dataset wrote its own set of translation rules"; now, "every dataset first fills in the same description sheet, and the program translates it, per that sheet, into a numeric language both distance and conjoint can read."

**Relation to the Exposé:**  
Module 1 originally belonged to P2, but it has already been started early this time, paving the way for Module 2 and Module 3 in P2.

---

### 9. Improvement two: the schema template already includes conjoint fields: *The template is ready for conjoint*

**What this slide should convey:**  
This time it is not just about cleaning data, but also about placing the information that later conjoint needs into the template in advance.

**How to present it:**  
The new `feature_schema_template.xlsx` describes not only the fields needed for distance analysis, such as data type and normalization method.  
It also adds the fields the later conjoint modules will use:

- `conjoint_role`: whether this field is a conjoint attribute;
- `conjoint_levels`: which selectable levels this attribute has;
- `conjoint_question_type`: whether the survey uses rating, pairwise, calibration, or WTP;
- `conjoint_section`: which part of the survey it belongs to.

**Why it matters:**  
From Module 2 onward, the survey can be generated automatically and directly from these fields.  
Module 3 can also use these fields to map survey answers back to attributes and levels.

**Example:**

Before, the smartphone `Feature_data` mainly only told the program:

- `price` is metric;
- `processor` is nominal;
- `battery` is ordinal;
- whether these fields enter distance analysis.

This is enough for a plain distance matrix.  
But it is not enough for conjoint, because the program still does not know "how to ask about it in the survey."

Now the schema template can add more:

- `transmission_type` is a conjoint attribute;
- its levels are `not synchronized; synchronized; powershift; CVT`;
- the question type is `rating`;
- it belongs to the `B1_rating` section.

This way, Module 2 does not have to manually redesign this question, but can generate the survey question automatically from the schema.

**Key takeaway:**  
The P1 schema is no longer designed only for the distance matrix, but is preparing for the conjoint pipeline.

---

### 10. Improvement three: one command runs the current baseline: *One command for the current baseline*

**What this slide should convey:**  
The current distance analysis baseline can already be reproduced reliably.

**How to present it:**  
You can now use the single command `./run.sh` to complete the main workflow of the current phase:

1. install or check dependencies;
2. run preprocessing for tractors / smartphones / user upload;
3. generate the plain technical distance matrix;
4. open the Streamlit dashboard.

**Why this matters for conjoint:**  
When Module 4 later builds the weighted distance, it needs to be compared against the current technical distance.  
So we must first have a stable, reproducible baseline.

**Example:**

| Dataset | Baseline the current one-command workflow can already produce |
|---|---|
| Tractor | 166 products, 43 processed features, producing a 166 × 166 technical distance matrix |
| Smartphone | 1020 products, 351 processed features, producing a 1020 × 1020 technical distance matrix |

Once Module 4 is done, the same set of products will produce another customer-weighted distance matrix.  
At that point the dashboard can compare: whether the products that are most similar technically and the products that are most similar after weighting by customer preferences are the same set.

**Key takeaway:**  
This step is not the final conjoint result, but it is the baseline for later comparison against the customer-weighted distance.

---

## Part 4: Mapping against the Exposé and the next step (pages 11-12)

### 11. P1 completion status: *Phase 1: foundation for conjoint*

**What this slide should convey:**  
Reconcile against the P1 tasks in the Exposé, and explain how these tasks support the conjoint goal.

| P1 task in the Exposé | Status | Delivered this time | Role for later conjoint |
|---|:---:|---|---|
| Run existing pipeline on all datasets | Done | tractors / smartphones / user upload can all produce results | Provides the technical baseline |
| Get Streamlit running for everyone | Done | `./run.sh`, dependency list, install instructions | Lets the team reproduce and keep developing |
| Define unified attribute schema | Done | schema template with validation | Module 2/3 read attributes and levels |
| Module 1: Universal Preprocessor | Started early | unified preprocessing engine | Data entry point for all later modules |

**How to present it:**  
P1 did not directly produce conjoint utilities or importance scores.  
Its role is to organize the original distance analysis tool into a foundation platform that can carry the conjoint modules.

---

### 12. Next steps: *Next: generate, compute, weight, compare*

**What this slide should convey:**  
Clearly explain what still has to be done from now to the final conjoint-based tool.

**How to present it:**  
According to the Exposé, the road ahead is:

1. **Module 2: Questionnaire Generator**  
   Automatically generate the conjoint survey from the schema.

2. **Module 3: Conjoint Computation**  
   Use the survey results to compute part-worth utility and relative importance.  
   This is where Nicolas's N=381 tractor reference needs to be reproduced.

3. **Module 4: Weighted Distance**  
   Put relative importance back into the distance matrix as weights.

4. **Module 5: Comparative Dashboard**  
   Compare technical distance and customer-weighted distance in the dashboard.

**Closing line:**  
What we have completed now is the foundation that goes from distance analysis toward conjoint analysis.  
The focus of the next phase is to truly turn customer preferences into weights, and let them change the distance calculation results.

---

## Notes

- The slide titles can stay in English, but the narrative storyline is recommended to change to "current distance baseline → conjoint extension → weighted customer view."
- Do not present P1 as "conjoint analysis is already complete." What P1 completed is the foundation refactor and the early start of Module 1.
- If you keep editing the HTML, prioritize changing pages 1-3 and pages 11-12, because these pages determine whether the audience understands the project direction.
