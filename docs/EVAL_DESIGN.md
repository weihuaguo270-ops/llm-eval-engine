# Eval 设计文档（Mid 档）

本文档描述 **llm-eval-engine** 的评测对象、指标口径、数据版本与复现方式。面试/简历请引用本文 + 对应快照日期。

## 1. 评什么

| 层级 | 对象 | 输出 |
|------|------|------|
| **Process Reward** | Agent 轨迹每一步 | 逐步得分、根因步、错误传播 |
| **Benchmark** | 固定任务集 × 模型 profile | 通过率、均分、失败 taxonomy |
| **Judge 校准** | Judge 输入片段 vs 人工分 | κ、MAE、held_out CI、标注者间 κ |

**不评：** 最终答案单一对错（那是 capability eval 的事）；本仓重点在 **过程质量** 与 **Judge 可信度**。

## 2. 怎么采信

### 2.1 三栏口径（必分）

| 栏 | 含义 | 能否写进简历 SLA |
|----|------|------------------|
| **offline / frozen** | 冻结 Judge 分或轨迹 | 否（验证机制） |
| **live Judge** | 真实 JudgeExecutor 当次重打分 | 趋势证据，绑定模型+日期 |
| **held_out** | 协议冻结后的独立样本 | **优先引用** |

### 2.2 Judge 校准门禁

- 默认阈值：held_out κ < **0.6** → `needs_calibration`
- 简历优先：**held_out live κ + bootstrap 95% CI**
- 标注者间：r1 vs r2，n≥50 才作强证据

### 2.3 Benchmark 门禁

- shipped baseline：`src/eval_engine/gates/baselines/benchmark_baseline.json`
- 回归阈值：均分下降 > **0.1**（5 分制）→ 阻塞
- CI：offline 跑批 + compare（无需 API Key）

## 3. 指标定义

| 指标 | 定义 | 范围 |
|------|------|------|
| `overall_score` | 步骤加权均分（根因步权 1.5） | 0–5 |
| `pass_rate` | 无需修正步骤占比 / 或用例通过率 | 0–1 |
| `passed`（用例） | 无低分步且 overall ≥ 3.5 | bool |
| Cohen's κ | Likert 1–5 整数类别一致率 | -1–1 |
| `failure_type` | wrong_tool / wrong_params / hallucination / error_propagation / … | 枚举 |

## 4. 数据版本（当前）

| 数据集 | 版本 | 规模 |
|--------|------|------|
| `benchmark_suite.json` | **v2** | **32** 条（tool 8 / rag 6 / search 6 / safety 6 / faith 6） |
| `calibration_human_judge.json` | **v5** | scored **70**，held_out **53**，r2 **53** |
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

offline 对比验证 **评分与归因逻辑**；live Judge 复跑验证 **Judge 在线稳定性**。  
完整 live Agent 换模：

```bash
pip install -e ../react-agent -e .
python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3
python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3 gpt-4o-mini
```

见 `examples/e2e_trajectory_eval.py` 与 `examples/run_benchmark_agent.py`。

## 7. 已知局限

1. Benchmark v2 轨迹为 ** curated 冻结样本**，非生产日志全量。
2. offline κ=1.0 **不能**替代 live Judge SLA。
3. 三模型 profile **不是**同一 Agent 框架实时换 API 的 live 跑批（需 react-agent 闭环扩展）。
4. r2 标注为 v5 协议化写入，真实盲标流程见 `docs/SECOND_RATER_PROTOCOL.md`。

## 8. 引用规范（简历）

✅ 可写：

- 「32 条 Process Reward benchmark，三模型 profile 对比」
- 「held_out n=53，标注者间 κ≈0.80（offline）」
- 「失败 taxonomy：幻觉 / 工具错 / 传播错误分布」

❌ 勿写：

- 「offline κ=1.0 证明线上 Judge 可靠」
- 「6 条小样本代表生产评测」（已扩容至 32，继续扩展中）
- 「三模型 live 大规模跑批」（除非已跑 `run_benchmark_live.py` 并附日期）
