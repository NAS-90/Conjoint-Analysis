# Results 页面逻辑:数据到图表的完整说明

本文档说明 **结果页(Conjoint Results)** 从本地问卷到每一个图表的完整逻辑,作为
代码与业务读出之间的桥梁。它是 [`questionnaire_logic.md`](./questionnaire_logic.md)
的下游:问卷收集到的答案,在这里被拟合成偏好结构并可视化。

入口与启动:

```bash
SURVEY_SPEC=questionnaire_spec_computers.json \
SURVEY_WORKBOOK=computer_survey_questions.xlsx \
  python -m streamlit run results_app.py
```

涉及的代码:

| 层 | 文件 | 职责 |
|----|------|------|
| 入口 | `results_app.py` | Streamlit 入口,只调用一个渲染函数 |
| 渲染 | `dashboard/results_dashboard.py` | 侧边栏 + 7 个板块的绘制(注入 `st`,可测试) |
| 分析核心 | `dashboard/results_analysis.py` | 纯计算:两套模型 + 五个分阶段统计 |
| 建模引擎 | `conjoint/acbc/estimate.py` | MNL 与 HB 拟合 |
| 模拟引擎 | `conjoint/acbc/simulation.py` | 份额(share of preference)与移除分析 |
| 读取 | `conjoint/acbc/responses.py` | 合并本地 `responses_*.csv` 问卷 |

---

## 1. 整体数据流

```
outputs/survey_responses_<product>/responses_*.csv   (本地问卷,一人一份)
        │  read_responses_dir()  合并成 long-format 大表(一文件 = 一受访者)
        ▼
analyze_survey_results(df, ...)        dashboard/results_analysis.py
        │  跑两套模型 + 五个分阶段统计
        ▼
SurveyResults  (一个不可变的 frozen dataclass 结果包)
        │
        ▼
render_results_dashboard()  渲染 7 个板块    dashboard/results_dashboard.py
```

输入是合并后的长表,每行是 `(respondent, stage, task_id, alternative_index, ...)`。
`stage` 有 5 种,**每个板块只读它需要的那个 stage**:

| stage | 来自问卷的哪一部分 | 喂给哪个板块 |
|-------|-------------------|-------------|
| `background` | Part A 背景 | 板块 ⑦ 人群画像 |
| `musthave` | B2 否决项(must-have / unacceptable) | 不直接出图(影响问卷阶段的 profile 生成) |
| `tournament` | B4 两两选择 | 建模引擎(MNL + HB)→ 板块 ①②③④⑤ |
| `calibration` | B5 购买意愿(0–5) | 板块 ⑥ 购买意愿 |
| `wtp` | Part C 愿付价档位 | 板块 ④ 愿付价(左栏) |

---

## 2. 侧边栏控件(三个输入)

`results_dashboard.py:_load_responses` + `render_results_dashboard`。

| 控件 | 作用 |
|------|------|
| **Data source** | `Local responses folder`(产品下拉,自动发现 `outputs/survey_responses_*`)或 `Upload questionnaires`(上传一份或多份)。读完做一个硬校验:**没有 tournament 行就报错退出**,因为 ACBC 估计完全依赖 B4 选择。 |
| **HB iterations** | 200–4000,HB 采样迭代次数。400 是预览档(Rhat 可能 > 1.1),≥ 4000 才是出版级。 |
| **Random seed** | HB 采样的随机种子,保证结果可复现。 |

产品下拉为自动发现:只要 `outputs/` 下多一个 `survey_responses_<product>` 文件夹,
菜单里就自动多一个选项(`_discover_response_dirs`),默认选中当前 spec 对应的产品。

---

## 3. 底层建模引擎(两套模型,只用 B4 的 tournament 行)

`analyze_survey_results` 里跑两个模型,这是理解整页的关键区分点。

### 3.1 MNL(多项 Logit,总体点估计)
`estimate.fit_from_responses(df)`

- 只取 tournament 行,把每个备选 profile 做 **effects coding**(每属性丢掉最后一个
  level 当基准),最大化选择似然,解出一组系数 `β`。
- `beta_to_level_utilities(β)` 把 `β` 还原成 **每个 level 的 part-worth 效用**
  (全样本平均口味)。
- **驱动:① 重要度、② part-worth、④ 衍生 WTP。**

### 3.2 HB(分层贝叶斯,逐人估计)
`estimate.fit_hb(df, n_iter, seed)`

- Metropolis-within-Gibbs 采样(纯 numpy),给 **每个受访者** 估一条自己的效用向量
  `β_i`,允许个体异质性。
- 产出 `hb_utilities`(每人一行)与 `rhat`(Gelman-Rubin 收敛诊断)。
- **驱动:① 收敛指标、⑤ 市场模拟器**(模拟器必须用个体效用,不能用平均)。

> 一句话区分:**柱状图(重要度、part-worth)来自 MNL 总体平均;模拟器与收敛指标
> 来自 HB 逐人估计。** 页面顶部 caption 笼统说 "Hierarchical Bayes",但重要度 /
> part-worth 这两张图实际取自合并后的 MNL 点估计。

---

## 4. 七个展示板块

每块标注:**数据来源 / 计算逻辑 / 展示**,以及对应的代码函数。

### ① Overview & convergence(总览)
`_render_overview`

- **数据**:tournament 行 + HB 的 `rhat`。
- **逻辑**:`Respondents` = tournament 里 unique 受访者数;`Tournament tasks` =
  `(respondent, task_id)` 分组数;`Rhat max` = HB 所有参数里最大的 Gelman-Rubin 值。
- **展示**:三个 metric。`Rhat < 1.1` 判为 "已收敛",否则提示 "预览档,加大迭代"。

### ② Attribute importance(属性重要度)
`_render_importance` + `estimate.attribute_importance`

- **数据**:MNL part-worths。
- **逻辑**:每个属性的重要度 = 该属性 part-worth 的 **极差**(最好 level 减最差
  level),再除以所有属性极差之和,得相对重要度 `Range_A / ΣRange`(和为 100%)。
  直觉:某属性 level 之间效用差越大,它对选择的影响越大。
- **展示**:横向条形图(升序),并用文字点出最重要的属性。

### ③ Part-worth utilities(分项效用)
`_render_partworths` + `estimate.rescale_zero_centered_diffs`

- **数据**:MNL `level_utilities`,经 `rescale_zero_centered_diffs` 缩放。
- **逻辑**:换算成 Sawtooth 风格的 **"zero-centered diffs"** 刻度(每属性内均值归零,
  全表平均极差缩放到 100),只为可读、可跨属性比较。值越高越被偏好。
- **展示**:选一个属性看它各 level 的条形图;展开可看全部属性的表。

### ④ Willingness-to-pay(愿付价,左右两栏)
`_render_wtp`

**左栏 Stated WTP(来自 Part C 实答)**,`summarize_wtp`:

- 每个升级特性,统计受访者落在各金额档(band)的人数,得到:众数档(modal)、
  `share_paid`(选了 "比最便宜档更高" 的人占比)、把档位标签里的 `$` 数字解析出来
  算 mean / median。
- 展示:汇总表 + 选定特性的档位分布图。

**右栏 Derived WTP(从价格效用反推)**,`derived_monetary_wtp`:

- 先求 **每效用单位值多少钱**:`usd_per_util = |Δ$| / |Δ效用|`(用价格档标签的区间
  中点当美元值,取跨价格 level 的斜率)。
- 再把其它每个 level 估值:`(该 level 效用 − 该属性最差 level 效用) × usd_per_util`。
- 价格缺失 / 标签解析不出 `$` / 价格效用是平的,则优雅降级显示提示,不报错。

### ⑤ Market simulator(市场模拟器)
`_render_simulator` + `conjoint/acbc/simulation.py`

- **数据**:HB 的逐人效用 `hb_utilities`。
- **逻辑**:你配 2–4 个产品(每属性选 level)。对 **每个受访者** 算每个产品的总效用
  = 各 level part-worth 之和,再 softmax,得这个人的 `share_of_preference`(logit 选择
  概率);`aggregate_shares` 对所有人取平均,即偏好份额。
- **移除分析**:`removal_impact` 算移除某产品前后的份额,看份额转移到哪。
- **展示**:份额条形图 + 移除后的 "前 / 后 / 变化" 表。

### ⑥ Purchase likelihood(购买意愿,B5)
`_render_calibration` + `summarize_calibration`

- **数据**:calibration 行的 0–5 评分。
- **逻辑**:`mean_probability_pct = 均值 / 5 × 100`;统计 0–5 各分的人数分布;并算
  每人均值。
- **展示**:平均购买意愿 metric + 0–5 分布图。

### ⑦ Respondent segments(人群画像,Part A)
`_render_segments` + `summarize_background`

- **数据**:background 行的实答。
- **逻辑**:按问题分组统计每个答案的出现次数(多选答案按 `;` 拆开分别计数)。
- **展示**:选一个背景问题,看答案分布的横条图。

---

## 5. 容错设计

整页对缺失 stage 做了优雅降级:

| 缺失 | 表现 |
|------|------|
| 没有 Part C | WTP 左栏显示提示 |
| 没有 B5 | 购买意愿板块提示 |
| 没有 Part A | 人群画像板块提示 |
| 价格无法解析 `$` | 衍生 WTP 显示提示 |
| **没有 tournament(B4)行** | **整页报错退出**(唯一硬性要求,无 B4 无法做 ACBC 估计) |

此外,拟合若抛异常,`render_results_dashboard` 用 try/except 兜住,显示
`Analysis failed: ...` 而不会让整页崩溃。

---

## 6. 速查:stage → 板块 → 模型

| 板块 | 读的 stage | 用的模型 / 统计 |
|------|-----------|----------------|
| ① 总览 | tournament | HB(Rhat) |
| ② 属性重要度 | tournament | MNL 极差占比 |
| ③ part-worth | tournament | MNL + 缩放 |
| ④ 愿付价(左) | wtp | 档位计数 |
| ④ 愿付价(右) | tournament | MNL 价格斜率反推 |
| ⑤ 市场模拟器 | tournament | HB 逐人 + logit 份额 |
| ⑥ 购买意愿 | calibration | 0–5 均值 / 分布 |
| ⑦ 人群画像 | background | 答案计数 |
