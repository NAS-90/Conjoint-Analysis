# 汇报大纲 · 从 Distance Analysis 走向 Conjoint Analysis

> 这份大纲是给 `refactor_report.html` 幻灯片用的。  
> 我重新读了 `../Docs/Expose_v3.md` 后，把主线改成下面这个逻辑：
>
> **现在的工具是 Distance Analysis。**  
> 它根据产品技术参数计算产品之间有多相似。
>
> **项目最终目标不是只做普通 distance analysis，而是加入 Conjoint Analysis。**  
> 也就是：先用问卷收集客户偏好，再把客户对不同属性的重视程度变成权重，最后让 distance matrix 反映“客户眼中的相似度”。
>
> 所以这次 P1 汇报要讲清楚：  
> 我现在做的不是最终 conjoint 模块，而是在把现有 distance analysis 工具改造成后续 conjoint 模块可以接上的基础。

---

## 第一部分：先讲清楚项目方向（第 1–3 页）

### 1. 封面 — *From Distance Analysis to Conjoint Analysis*

**这一页要表达：**  
这次汇报不是单纯讲代码重构，而是讲第一阶段如何为最终的 conjoint analysis 工具打基础。

**可以怎么讲：**  
现在我们手里的工具叫 Distance Analysis。它能根据产品参数算出哪些产品相似、哪些产品差异大。  
但 Exposé 里的最终目标更进一步：把客户偏好加入进来，让工具不仅看技术参数，也能看客户真正关心什么。

**听众该记住：**  
当前阶段是从 distance analysis 走向 conjoint analysis 的第一步。

---

### 2. 当前工具和最终目标 — *Technical distance today, customer-weighted distance next*

**这一页要表达：**  
当前工具和最终目标之间的差别。

**可以怎么讲：**  
现在的 distance analysis 主要回答这个问题：

> 从产品参数来看，哪些产品彼此相似？

但最终的 conjoint-based tool 要回答的是：

> 从客户偏好来看，哪些产品真的彼此相似？

这两个答案可能不一样。  
两个产品在技术参数上很接近，但如果客户最在意的属性不同，它们在客户眼里可能并不相似。

**屏幕上建议放：**

| 当前版本 | 目标版本 |
|---|---|
| Technical Distance Analysis | Conjoint-weighted Distance Analysis |
| 所有属性默认差不多重要 | 属性重要性来自客户问卷 |
| 看工程参数 | 看客户偏好 + 工程参数 |
| 输出普通 distance matrix | 输出 technical vs customer-weighted 对比 |

**和 Exposé 的关系：**  
对应 Exposé 第 1–3 节：现有工具能算技术距离，但缺少客户视角。

---

### 3. 为什么需要 Conjoint — *Not every feature matters equally*

**这一页要表达：**  
Exposé 里指出的核心问题：现在的 distance analysis 默认每个属性一样重要。

**可以怎么讲：**  
目前的距离计算会把所有特征标准化，然后基本按同等重要性参与计算。  
这在技术上可以跑通，但它不一定符合客户真实决策。

举例来说：  
如果客户非常在意 transmission，但不太在意 tank size，那么这两个属性在距离计算里就不应该有一样的影响力。

**重点句：**  
Conjoint analysis 的作用，就是把“客户觉得什么重要”转换成数字权重。

**简单例子：**  
现在的 technical distance 可能会把 `transmission_type`、`tank_capacity`、`wheelbase` 都当成参与距离计算的普通属性。  
但如果问卷结果显示客户最在意的是 `transmission_type`，不太在意 `wheelbase`，那么后面的 conjoint-weighted distance 就会让 transmission 的差异影响更大，wheelbase 的差异影响更小。

**听众该记住：**  
Conjoint 不是另一个独立展示功能，而是后面要反过来改变 distance calculation 的核心输入。

---

## 第二部分：P1 为什么先修基础（第 4–6 页）

### 4. 后续模块需要一个稳定的数据入口 — *Conjoint needs clean metadata*

**这一页要表达：**  
要自动生成问卷、计算 conjoint、再加权距离，前提是数据结构必须统一。

**可以怎么讲：**  
Exposé 把后续工作拆成五个模块：

1. Universal Preprocessor；
2. Questionnaire Generator；
3. Conjoint Computation；
4. Weighted Distance；
5. Comparative Dashboard。

这些模块不是各做各的。  
Module 2 要读产品属性生成问卷，Module 3 要知道每个属性有哪些 level，Module 4 要把 conjoint 权重映射回 distance matrix。  
所以最前面的数据 schema 如果不稳定，后面所有 conjoint 模块都会接不上。

**听众该记住：**  
P1 的重构不是为了“代码好看”，而是为了让后面的 conjoint pipeline 有统一入口。

---

### 5. 原问题一：数据清洗逻辑不统一 — *The same preprocessing was repeated*

**这一页要表达：**  
旧工具虽然能跑 distance analysis，但不是一个适合扩展到 conjoint 的架构。

**可以怎么讲：**  
原来不同数据集有不同的预处理脚本。  
它们都在做类似的事情：清洗表格、转换数据、准备 distance matrix。  
这对一个 demo 来说可以，但对后续五个模块来说风险很大。

**为什么影响 conjoint：**  
如果拖拉机、手机、用户上传数据各自用不同规则清洗，那么后面自动生成问卷和计算权重时，就很难保证它们读到的是同一种数据结构。

**用一个 distance analysis 小例子来理解：**

Distance analysis 不能直接拿原始 Excel 来算。  
它最后需要的是一张“全是数字”的产品表，因为距离计算本质上是在比较两行数字有多接近。

以 tractor 数据为例，原始 `Edited` 表里可能长这样：

| product | hp_range | transmission_type | tank_capacity |
|---|---:|---|---:|
| MF Essential II | `61-70` | `Synchronized` | 85 |
| MF Standard II | `61-70` | `Not Synchronized` | 85 |
| MF Premium | `71-80` | `Powershift` | 105 |

但这张表不能直接算距离，因为里面有区间、文字类别、不同类型的字段。  
所以程序还要读 `Feature_data` 这张说明表：

| feature_name | data_types | normalization_method | ideal_direction |
|---|---|---|---|
| hp_range | ordinal | ordinal-mapping | higher |
| transmission_type | nominal | none | neutral |
| tank_capacity | metric | z-score | higher |

预处理之后，程序会把它变成 distance analysis 可以使用的数字表：

| product | hp_range | transmission_Synchronized | transmission_Not_Synchronized | transmission_Powershift | tank_capacity |
|---|---:|---:|---:|---:|---:|
| MF Essential II | 65.5 | 1 | 0 | 0 | 85 |
| MF Standard II | 65.5 | 0 | 1 | 0 | 85 |
| MF Premium | 75.5 | 0 | 0 | 1 | 105 |

然后 distance matrix 才能比较：

|  | Essential II | Standard II | Premium |
|---|---:|---:|---:|
| Essential II | 0 | 小距离 | 大一点 |
| Standard II | 小距离 | 0 | 大一点 |
| Premium | 大一点 | 大一点 | 0 |

**没有 unified preprocessor 的问题：**

- tractor 脚本要自己知道 `61-70` 应该转成 65.5；
- smartphone 脚本又要自己知道 `₹54,999.00` 要去掉货币符号和逗号；
- 如果再来一个 bicycle 数据集，又要再写一套 bicycle 规则；
- 后面的 conjoint 模块也要分别理解每个数据集的特殊格式。

**现在 unified preprocessor 的效果：**

- 不管是 tractor、smartphone 还是 user upload，都先用同一种 `Feature_data` schema 描述字段；
- 程序根据 schema 判断每列是 metric、ordinal、binary 还是 nominal；
- 程序统一输出 `preprocessed_output.csv`；
- distance matrix 和后面的 conjoint 模块都只需要读取这个统一输出。

**听众该记住：**  
Conjoint 模块需要统一数据语言，不能建立在几套重复脚本上。

---

### 6. 原问题二：别人很难复现流程 — *Hard to run, hard to build on*

**这一页要表达：**  
P1 还要解决“团队其他人能不能跑起来”的问题。

**可以怎么讲：**  
如果一个队友想继续做 Module 2 或 Module 3，他不能先花很多时间猜：

- 要装哪些依赖；
- 先跑哪个文件；
- 结果文件在哪里；
- 哪个输出可以给下一个模块用。

如果基础流程不清楚，后面做 questionnaire、conjoint computation 和 weighted distance 都会被拖慢。

**和 Exposé 的关系：**  
P1 的任务包括 run existing tool、get Streamlit running for everyone、define unified attribute schema。  
这些都是后续 P2/P3 的前置条件。

**听众该记住：**  
这次 P1 的价值，是让后续模块可以在同一个可复现的基础上继续开发。

---

## 第三部分：这次 P1 我具体改了什么（第 7–10 页）

### 7. 核心思路 — *One schema connects distance and conjoint*

**这一页要表达：**  
新设计的核心不是只服务 distance analysis，而是同时为 distance 和 conjoint 准备数据。

**可以怎么讲：**  
现在用户不只是上传产品数据，还要在 `Feature_data` 里描述每个属性：

- 这个属性是什么类型；
- 是否参与分析；
- 怎么标准化；
- 在 conjoint 里是不是一个 attribute；
- 有哪些 conjoint levels；
- 应该出现在问卷的哪个部分。

这样同一份 schema 可以同时服务两个方向：  
前面给 distance matrix 用，后面给 questionnaire generator 和 conjoint computation 用。

**听众该记住：**  
schema 是 distance analysis 和 conjoint analysis 之间的桥。

---

### 8. 改进一：预处理变成通用 Module 1 — *A universal preprocessor*

**这一页要表达：**  
我已经把旧的预处理逻辑整理成 Module 1 的基础版本。

**可以怎么讲：**  
现在核心清洗逻辑集中在 `preprocessing.py` 里。  
拖拉机、手机、用户上传数据都可以通过同一个 universal preprocessor 处理，而不是各自维护一套规则。

**它为 conjoint 准备了什么：**

- 统一读取 `Edited` 和 `Feature_data`；
- 输出可计算的 `preprocessed_output.csv`；
- 保留后续模块需要的属性 metadata；
- 让不同产品类别走同一个入口。

**实际流程对比：**

以前的流程更像这样：

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

问题是：两个数据集虽然最后都要进入 distance analysis，但前面的清洗规则分散在不同地方。  
如果后面要做 conjoint questionnaire，就很难复用这套流程。

现在的流程变成：

```text
Any product Excel
  → Edited sheet: raw product data
  → Feature_data sheet: tells the program how to read each column
  → universal preprocessing.py
  → one numeric preprocessed_output.csv
  → distance matrix now
  → questionnaire / conjoint / weighted distance later
```

**具体对比：**

| 原始数据 | schema 告诉程序 | 统一预处理输出 | 后面怎么用 |
|---|---|---|---|
| Tractor `hp_range = 61-70` | 这是 ordinal，数值越高越好 | `65.5` | 可进入 technical distance；以后也能作为 conjoint attribute |
| Tractor `transmission_type = Synchronized` | 这是 nominal，有多个 level | `transmission_Synchronized = 1` | 可比较配置差异；以后可生成 transmission 问卷题 |
| Smartphone `price = ₹54,999.00` | 这是 metric，价格越低越好 | `54999` 再标准化 | 可进入 technical distance；以后可做价格相关分析 |
| Smartphone `os = Android v13` | 这是 nominal | `os_Android_v13 = 1` | 可比较系统差异；以后可决定是否进入 conjoint |

可以口头讲成一句话：  
以前是“每个数据集自己写一套翻译规则”；现在是“所有数据集都先填同一种说明表，程序按说明表翻译成 distance/conjoint 都能读的数字语言”。

**和 Exposé 的关系：**  
Module 1 原本属于 P2，但这次已经提前开始，为 P2 的 Module 2 和 Module 3 铺路。

---

### 9. 改进二：schema 模板已经包含 conjoint 字段 — *The template is ready for conjoint*

**这一页要表达：**  
这次不只是清洗数据，也把后续 conjoint 需要的信息提前放进模板。

**可以怎么讲：**  
新的 `feature_schema_template.xlsx` 不只描述 distance analysis 所需字段，比如数据类型和标准化方法。  
它还加入了后续 conjoint 模块会用到的字段：

- `conjoint_role`：这个字段是不是 conjoint attribute；
- `conjoint_levels`：这个属性有哪些可选 level；
- `conjoint_question_type`：问卷里用 rating、pairwise、calibration 还是 WTP；
- `conjoint_section`：它属于问卷的哪个部分。

**为什么重要：**  
Module 2 以后可以直接根据这些字段自动生成问卷。  
Module 3 也能根据这些字段把问卷答案映射回属性和 level。

**实际例子：**

以前 smartphone 的 `Feature_data` 主要只告诉程序：

- `price` 是 metric；
- `processor` 是 nominal；
- `battery` 是 ordinal；
- 这些字段要不要进入 distance analysis。

这对普通 distance matrix 已经够用。  
但对 conjoint 还不够，因为程序还不知道“问卷里要怎么问”。

现在 schema template 可以继续补充：

- `transmission_type` 是 conjoint attribute；
- 它的 levels 是 `not synchronized; synchronized; powershift; CVT`；
- 问卷题型是 `rating`；
- 它属于 `B1_rating` 部分。

这样 Module 2 就不用人工重新设计这道题，而是可以从 schema 里自动生成问卷题目。

**听众该记住：**  
P1 的 schema 已经不是只为 distance matrix 设计，而是在为 conjoint pipeline 做准备。

---

### 10. 改进三：一条命令跑通当前基线 — *One command for the current baseline*

**这一页要表达：**  
当前 distance analysis 基线已经可以稳定复现。

**可以怎么讲：**  
现在可以用 `./run.sh` 一条命令完成当前阶段的主要流程：

1. 安装或检查依赖；
2. 对 tractors / smartphones / user upload 跑预处理；
3. 生成普通 technical distance matrix；
4. 打开 Streamlit dashboard。

**为什么这对 conjoint 重要：**  
后面 Module 4 要做 weighted distance 时，需要和当前 technical distance 做对比。  
所以我们必须先有一个稳定、可复现的 baseline。

**实际例子：**

| 数据集 | 当前一键流程已经能产出的 baseline |
|---|---|
| Tractor | 166 个产品，43 个处理后的特征，生成 166 × 166 的 technical distance matrix |
| Smartphone | 1020 个产品，351 个处理后的特征，生成 1020 × 1020 的 technical distance matrix |

等 Module 4 完成后，同一批产品会再生成一份 customer-weighted distance matrix。  
到时候 dashboard 就可以对比：技术上最相似的产品，和客户偏好加权后最相似的产品，是不是同一批。

**听众该记住：**  
这一步不是最终 conjoint 结果，但它是之后对比 customer-weighted distance 的基准线。

---

## 第四部分：对照 Exposé 和下一步（第 11–12 页）

### 11. P1 完成情况 — *Phase 1: foundation for conjoint*

**这一页要表达：**  
用 Exposé 的 P1 任务来对账，同时说明这些任务如何支撑 conjoint 目标。

| Exposé 里的 P1 任务 | 状态 | 这次交付 | 对后续 conjoint 的作用 |
|---|:---:|---|---|
| Run existing pipeline on all datasets | 完成 | tractors / smartphones / user upload 都能生成结果 | 提供 technical baseline |
| Get Streamlit running for everyone | 完成 | `./run.sh`、依赖清单、安装说明 | 让团队能复现和继续开发 |
| Define unified attribute schema | 完成 | 带 validation 的 schema template | Module 2/3 读取属性和 levels |
| Module 1: Universal Preprocessor | 提前开始 | 统一预处理引擎 | 后续所有模块的数据入口 |

**可以怎么讲：**  
P1 没有直接产出 conjoint utilities 或 importance scores。  
它的作用是把原来的 distance analysis 工具整理成一个可以承接 conjoint 模块的基础平台。

---

### 12. 下一步路线 — *Next: generate, compute, weight, compare*

**这一页要表达：**  
清楚说明从现在到最终 conjoint-based tool 还要做什么。

**可以怎么讲：**  
根据 Exposé，后面的路线是：

1. **Module 2：Questionnaire Generator**  
   根据 schema 自动生成 conjoint 问卷。

2. **Module 3：Conjoint Computation**  
   用问卷结果计算 part-worth utility 和 relative importance。  
   这里要复现 Nicolas 的 N=381 tractor reference。

3. **Module 4：Weighted Distance**  
   把 relative importance 作为权重放回 distance matrix。

4. **Module 5：Comparative Dashboard**  
   在 dashboard 里对比 technical distance 和 customer-weighted distance。

**收尾句：**  
现在我们完成的是从 distance analysis 走向 conjoint analysis 的地基。  
下一阶段的重点，是把客户偏好真正转成权重，并让它改变距离计算结果。

---

## 备注

- 幻灯片标题可以继续用英文，但叙事主线建议改成“current distance baseline → conjoint extension → weighted customer view”。
- 不要把 P1 讲成“已经完成 conjoint analysis”。P1 完成的是基础改造和 Module 1 的提前起步。
- 如果继续改 HTML，优先把第 1–3 页和第 11–12 页改掉，因为这些页决定听众是否理解项目方向。
