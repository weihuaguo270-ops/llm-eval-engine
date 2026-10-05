# 本仓库的项目级指令

> DSH 从仓库根加载本文件。它比 `~/.dsh/AGENTS.md`（用户全局）**更具体，故优先**。
> 通用写法规则见全局文件；本文件定**本项目的指称要求、术语准入与本仓库既有约定**。

## 一、术语：先能指称，再谈写法

### A. 指称义务（**最重要的一条**）

> 凡是用来**指称仓库里某个对象**的名词/术语，都必须能指出它在仓库里的落点
> （文件:行 / 字段 / 函数 / 数据文件）。
> **指不出来 = 这个词不该用。这不是风格问题，是错。**
>
> **范围只限于"指称对象"的词**——「文件」「结论」「原因」这类普通名词不受约束。
> 判断法：把它换成"那个东西"，句子还成立吗？成立 → 普通名词；不成立 → 它在命名一个对象，**必须能指称**。

自查一句话：**「这个词，我指得出仓库里的哪个东西？」**

默认方向与本仓既有纪律一致：本仓是「**未标不得当作通过**」，这里是
「**未登记 / 无指称不得使用**」——**未禁止 ≠ 允许**。

已挡住的三例（都是我自己造的词）：

| 我造的词 | 指称结果 | 结论 |
|---|---|---|
| 「题」 | 仓库里没有任何字段/类/文件叫它；已跟踪 `*.md` 里连「抽取」都 0 处，「题」只出现在我写的对标文档里 | **不得使用** |
| 「抽取器」 | Python 里只有 `extract*` **函数名**（如 `extract_judge_score`、`extract_step_artifacts`），没有任何对象叫 extractor | **不得使用** |
| `rubric_fingerprint` | `git grep` 命中 **0**；真名是 `rubric_boundary_sha256` | **不得使用** |

### B. 准入程序

要引入仓库里没有的词：**先**在 C 表登记（所指对象 + 代码落点 + 英文），**再**使用。
**登记之前不得出现在解释里。**

### C. 写法表（同一所指的固定写法；**只有通过 A 之后才适用**）

| 所指（仓库里的东西） | 落点（证据） | 固定写法 | 英文 |
|---|---|---|---|
| 评测单位：数据集里的一行 / 一条被执行的对象 | `case_id`、`CaseResult`、`case_fingerprint()`、`core/eval_contracts.py`「评测用例级契约」 | **用例** | **`case`** |
| 搜索线送给 agent 的那条输入 | 请求池条目（如 `w15`）；归档 `build_request_level_batch.py`（"请求级"） | **请求** | **`request`** |
| 凭什么选它的记录 | `POOL_PROVENANCE`、`meta.pool_provenance`、`meta.sampling`、`selection_manifest.json`、`rejection_ledger.json` | **出处 / 选取理由** | **`provenance` / `selection rationale`** |
| 整份"为什么这样构成"的对外说明 | **尚无**（业界对应物是 datasheet） | **数据说明** | **`datasheet`** |
| Rubric 体系 | `docs/RUBRIC_EVAL_EXTERNAL_BENCHMARK.md`、`rubric_quality_report.py` | **Rubric**（首字母大写） | **Rubric** |
| Rubric 指纹 | 报告字段 `reproducibility.rubric_boundary_sha256` | **Rubric 指纹**；只在指字段时才写全名 | — |
| 一般意义的判准／依据 | `scripts/check_inline_quotes.py` 的"判定依据" | **判定依据** | **`criterion`** |
| 留出划分 | 数据划分名 `held_out` | **`held_out`** | `held_out` |
| 变体账本 | 代码符号 `variant_ledger` | **变体账本**；代码里写 `variant_ledger` | `variant ledger` |
| 标注者间一致性 | 报告里的 κ / `Krippendorff α` | **κ**；加权版写「线性加权 κ」「有序 α」 | `kappa` |
| 失败码通道 | `code_channel_status()` | **失败码通道**；代码里写 `code_channel_status` | — |
| 可判率 / 覆盖率 / 缺陷率 | `MIN_JUDGED_FOR_RATE`、`coverage_report_state()`、缺陷率 | **中文** | 不写 judgeable rate / coverage / defect rate |
| 抽样 / 分层 / 配额 / 预注册 | `select_archived_quota.py`、`_coverage_gate`、`prereg/*` | **中文**（首次可括注英文一次） | sampling / stratification / quota / preregistration |
| 按请求聚簇的自助法 | `clustered_rate_ci`（`core/verdict.py`） | **中文** | 不写 clustered bootstrap |
| 步状态取值 | `success` / `tool_error` / `no_content` | **保持原文**（真实枚举值） | 同左 |
| 口径 / 锚点 / 退化 / 冗余 | 口径数据、`SCALE_ANCHORS`、`degenerate`、`REDUNDANCY_MIN_N` | **中文** | — |

### D. 已废止的写法（**只记已作出的决定，不是禁用词清单**——新词一律走 A/B）

| 废止 | 原因 | 替代 |
|---|---|---|
| 「判据」 | **歧义**：既指 Rubric 体系，又指一般意义的判准 | 指 Rubric → **Rubric**；指判准 → **判定依据** |
| 「题／题目」 | **无指称**：仓库里没有这个对象。它是对标材料里**外部** benchmark 的单位词 | 本仓 → **用例 / `case`** 或 **请求 / `request`**；对标外部时用那家的词（`instance`／`question`／`task`／`doc`）并注明是哪一家 |

（「判据」已于 2026-10-05 全仓替换：**已跟踪文件 0 处**；归档 `reports/` 里的原文保留。）

## 二、对标材料的专有名词（保持原文，不译）

Inspect AI、lm-eval-harness、OpenAI Evals、HELM、Efficient-HELM、SWE-bench Verified、
HealthBench（含 HealthBench Hard）、SimpleQA、CRAG、FreshQA、BrowseComp、DeepResearch Bench、
Krippendorff α。

## 三、本仓库的既有约定（均已核实）

- 每个脚本开头写 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`。
- 测试用 `importlib.util.spec_from_file_location` 按路径加载 `scripts/*.py`；
  **不要 import 归档代码**——它依赖已被 `git rm` 的模块，只能按函数单独编译执行。
- `reports/` 在 `.gitignore` 内 → **git 回滚不了它**；依赖归档副本的测试必须在副本缺失时**跳过**。
- 原则：**机制活下来、口径随线走**（被撤销那条线的口径数据随线归档，通用机制留在 `src/`）。
- **未标不得当作通过**；`unbanded` 不等于"零缺陷"。
- 结论必须自带限定：样本量不够时**只报计数不报率**；**两个口径不得混成一个数**。
- 改 Python 前先跑 `python scripts/check_inline_quotes.py`（扫双引号串里误写 ASCII 引号那类语法错误）。

## 四、例外

引用仓库既有文档原文、**归档 `reports/` 里的原文**、代码标识符、报错信息时按原文；
用户明确要求用英文时以用户要求为准。
