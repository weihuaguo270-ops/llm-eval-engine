# Eval 设计文档

本文档是 **llm-eval-engine** 的评测设计说明，约定评测范围、指标口径、数据版本与复现方式。对外引用数字时，以本文 + [`METRICS_TRUST.md`](METRICS_TRUST.md) + 对应日期快照为准。

## 1. 评什么

| 层级 | 对象 | 输出 |
|------|------|------|
| **Process Reward** | Agent 轨迹每一步 | 逐步得分、根因步、错误传播 |
| **Benchmark** | 固定任务集 × 模型 profile | 通过率、均分、失败 taxonomy |
| **Judge 校准** | Judge 输入片段 vs 人工分 | κ、MAE、MSE/RMSE、held_out CI、标注者间 κ |

**不评：** 最终答案单一对错（由 react-agent `eval/` 等 capability eval 负责）；本仓聚焦 **过程质量** 与 **Judge 可信度**。

## 2. 怎么采信

### 2.1 三栏口径（必分）

| 栏 | 含义 | 能否作为对外 SLA |
|----|------|------------------|
| **offline / frozen** | 冻结 Judge 分或轨迹 | 否（验证机制） |
| **live Judge** | 真实 JudgeExecutor 当次重打分 | 趋势证据，须绑定模型与日期 |
| **held_out** | 协议冻结后的独立样本 | **引用优先** |

### 2.2 Judge 校准门禁

- 默认阈值：held_out κ < **0.6** → `needs_calibration`
- 对外基准：**held_out live κ + bootstrap 95% CI**
- 标注者间：r1 vs r2，n≥50 才作强证据

### 2.3 Benchmark 门禁

- shipped baseline：`src/eval_engine/gates/baselines/benchmark_baseline.json`
- 回归阈值：均分下降 > **0.1**（5 分制）→ 阻塞
- CI：offline 跑批 + compare（无需 API Key）

## 3. 指标定义

| 指标 | 定义 | 范围 |
|------|------|------|
| `overall_score` | 步骤加权均分（根因步权 1.5）；**没有任何步被评分时为 `None`（未评估），不是 0 分** | 0–5 或 `None` |
| `pass_rate` | 无需修正步骤占比 / 或用例通过率 | 0–1 |
| `passed`（用例） | 至少一步被评分、无低分步且 overall ≥ 3.5 | bool |
| Cohen's κ | Likert 1–5 **整数类别**一致率 | -1–1 |
| MAE / Bias（Likert） | 整数档上的平均绝对误差 / 系统性偏差 | ≥0 / 实数 |
| MSE / RMSE / MAE（连续） | 把分当 **1.0–5.0 实数**（可输出 3.7、4.2），衡量幅度误差 | ≥0 |
| `failure_type` | wrong_tool / wrong_params / hallucination / error_propagation / … | 枚举 |

### 3.1 双视角：类别 vs 连续回归

人机校准默认同时报告两套口径（见 `calibration.agreement_table` / `regression_metrics`）：

| 视角 | 分数怎么看 | 主指标 | 回答的问题 |
|------|------------|--------|------------|
| **类别（Likert）** | 四舍五入到 1–5 整数档 | κ、精确一致、±1、混淆矩阵 | 「有没有落在同一档？」 |
| **连续回归** | 裁剪到 [1.0, 5.0] 的任意实数 | MSE、RMSE、连续 MAE、bias | 「预测值和真值差多远？」 |

- 类别设定保留门禁与对外 κ 口径；连续指标补「幅度」——例如 human=4、judge=3.7 在 κ 上可能仍算同档（round 后都是 4），但 MSE 会记下 0.09 的平方误差。
- Judge / 标注允许输出小数分；计算前统一 `_to_continuous` 裁剪，避免越界。
- 报告里 `mae` / `bias` 仍为 **整数档**（兼容历史快照）；连续幅度见 `mse` / `rmse` / `regression.*`。

### 3.2 结果判断（决策级）

κ 回答「**分数是否一致**」，**不回答「这批数据支持什么结论」**。为此单列一层**结果判断**，与 κ **并列、不合成**。

**合格线**（逐字来自金标准 `meta.labeling_protocol` 的刻度锚点；落盘为 `src/eval_engine/dataset/data/verdict_bands_line1.json`，**含出处**）：

| 判定 | 分数 | 锚点依据 |
|------|------|----------|
| `pass` | 4–5 | 基本正确可接受瑕疵 / 符合协议且无明显问题 |
| `marginal` | 3 | 勉强可用 / **有实质缺陷**（单列：不算缺陷，也不等于通过） |
| `defect` | **1–2** | 失败/幻觉/危险；明显不当但未完全灾难 |
| `undecidable` | na / unattr / oos | Judge 弃权或不可判 |
| `blank` | 空 | **未标——不得当合格**；`unbanded`（该维度无合格线）**同样不得当合格** |

```bash
python examples/run_result_evaluation.py --split held_out        # 默认取最近一份 live 报告
python examples/run_result_evaluation.py --report <报告.json> --split dev
```

**输出**：逐 template 的判定分布、**缺陷率 + item 级 95% CI**、**决策级一致率**、
**误杀**（人判非缺陷而 Judge 判缺陷）/ **漏杀**（人判缺陷而 Judge 放过）、判定交叉表。

**为什么必须与 κ 并列**：κ 把「1↔2」（缺陷带内）与「2↔3」（跨带）同等看待，但**只有跨带分歧翻转结论**。
例：v2.1 live 分数级 κ=0.8565（5 处分歧），而**决策级一致率 96.2%（51/53）**——5 处里 3 处是缺陷带内的 1↔2。
**只报 κ 既低估判据可用性，也找不准该改的边界。**

**引用纪律**
- 报告头部按报告自带 `mode` **自动标注栏位**，**非 live 栏会打出告警**——frozen 栏只证明「复现一致」，
  **不得作 Judge 可信度或结果判断的依据**；
- 判定用的合格线**必须带出处**（本仓逐字引用刻度锚点），不得另立一套；
- **簇 < 10 时不报聚簇 CI**（簇太少会退化成窄区间；文本线只有 3 个 template → 只报 item 级 CI）；
- 判据文本指纹见报告 `reproducibility.rubric_boundary_sha256`。

## 4. 数据版本（当前）

| 数据集 | 版本 | 规模 |
|--------|------|------|
| `benchmark_suite.json` | **v2** | **32** 条（tool 8 / rag 6 / search 6 / safety 6 / faith 6） |
| `calibration_human_judge.json` | **v5** | scored **70**，held_out **53**，r2 **53**（2026-10-01 重标） |
| `golden.json` | — | 9 条（capability 种子，待合并进 benchmark） |

## 5. 复现命令

```bash
# Benchmark offline（CI 同款）
python examples/run_benchmark.py
python examples/run_benchmark.py --compare

# Benchmark live Judge（需 API Key）
python examples/run_benchmark_live.py

# Judge 校准 offline
python examples/run_calibration.py

# Judge 校准 live held_out
python examples/run_calibration.py --live --split held_out

# 结果判断（决策级：缺陷率 / 决策级一致率 / 误评·漏评）
python examples/run_result_evaluation.py --split held_out

# 端到端：轨迹 → 评分 → 报告
python examples/e2e_trajectory_eval.py

# 全量测试
pytest tests/ -q
```

## 6. 模型 profile 说明（Benchmark）

三模型 **deepseek-v3 / gpt-4o-mini / qwen-plus** 表示 **不同 Agent 行为档位** 的冻结轨迹：

- **strong**：工具正确、忠实、安全
- **medium**：轻微瑕疵或冗余
- **weak**：工具错、幻觉、安全问题

offline 对比用于验证 **评分与归因逻辑**；live Judge 复跑用于验证 **Judge 在线稳定性**。  
live Agent 换模闭环：

```bash
pip install -e ../react-agent -e .
python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3
python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3 gpt-4o-mini
```

见 `examples/e2e_trajectory_eval.py` 与 `examples/run_benchmark_agent.py`。

## 7. 已知局限

1. Benchmark v2 轨迹为 **curated 冻结样本**，非生产日志全量。
2. offline κ=1.0 **不能**替代 live Judge SLA。
3. 三模型 profile **不是**同一 Agent 框架实时换 API 的 live 跑批（需 react-agent 闭环扩展）。
4. r2 已按 `docs/SECOND_RATER_PROTOCOL.md` 真人盲标回填（2026-10-01）；标注者间 κ 见 `METRICS_TRUST.md`。

## 8. 引用指标时的要求

写 README、Release Notes 或对外报告时：

- 写明数据集版本与快照日期（如 benchmark v2、calibration v5、**2026-10-01**）
- 分栏引用 offline / live / held_out，不合成单一「总分」
- 优先引用 **held_out live κ + bootstrap 95% CI**（当前见 `docs/METRICS_TRUST.md`）

**可接受的引用形态：**

- 「32 条 Process Reward benchmark，三模型 profile 对比（offline，日期…）」
- 「held_out n=53，live κ≈0.86（DeepSeek，2026-10-01，边界 v2.1）」
- 「失败 taxonomy：幻觉 / 工具错 / 传播错误分布」

**不要这样写：**

- 「offline κ=1.0 证明线上 Judge 可靠」
- 「小样本可代表生产评测」（当前 benchmark 32 条，按需扩展）
- 「三模型 live 大规模跑批」（除非已跑 live 脚本并附日期与报告链接）