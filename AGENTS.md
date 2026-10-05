# 本仓库的项目级指令

> DSH 从仓库根加载本文件。它比 `~/.dsh/AGENTS.md`（用户全局）**更具体，故优先**。
> 通用写法规则见全局文件；本文件只定**本项目的术语落点**与本仓库的既有约定。

## 一、术语落点（在本仓库内一律照此写，不再切换）

| 概念 | 固定写法 | 说明 |
|---|---|---|
| Rubric 体系 | **Rubric** | 叙述时首字母大写。**全仓一律用它**，不再写"判据"（归档 `reports/` 里的原文除外） |
| 一般意义的判准／依据 | **判定依据** | **不要写成 Rubric**——它不是 Rubric 体系（例：`check_inline_quotes.py` 的判定依据、`process_reward.py` 的"作判定依据"） |
| Rubric 指纹 | 叙述写 **Rubric 指纹** | 只在**指具体字段**时才写 `reproducibility.rubric_boundary_sha256`；**勿写 `rubric_fingerprint`——该符号在仓库里不存在** |
| 留出划分 | **`held_out`** | 标识符，保持原文；不写"留出集" |
| 变体账本 | **`variant_ledger`** | 代码符号；叙述时说"变体账本" |
| 标注者间一致性 | **κ** | 符号；加权版写"线性加权 κ"、"有序 α" |
| 失败码通道 | **失败码通道** | 中文；代码里的 `code_channel_status` 保持原文 |
| 可判率 / 覆盖率 / 缺陷率 | **中文** | 不写 judgeable rate / coverage / defect rate |
| 抽样 / 分层 / 配额 / 预注册 | **中文** | 首次出现可括注英文一次，之后只用中文 |
| 按请求聚簇的自助法 | **中文** | 不写 clustered bootstrap |
| 步状态取值 | **`success`** / **`tool_error`** / **`no_content`** | **真实枚举值**，保持原文 |
| 口径 / 锚点 / 退化 / 冗余 | **中文** | |

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

引用仓库既有文档原文、代码标识符、报错信息时按原文；用户明确要求用英文时以用户要求为准。
