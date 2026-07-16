# LLM Eval Engine

[![CI](https://github.com/weihuaguo270-ops/llm-eval-engine/actions/workflows/test.yml/badge.svg)](https://github.com/weihuaguo270-ops/llm-eval-engine/actions/workflows/test.yml) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**LLM 评估实验框架**，支持 process-level LLM-as-Judge 步骤评分、动态评分标准生成、自适应 Eval Loop 和人工审批介入。

> 术语边界：本项目的 `Process Reward` 是基于 Judge LLM 的过程级评分流程，不是训练得到的 Process Reward Model（PRM），也不提供 PRM 训练数据或损失函数。

## 为什么需要这个框架

传统 LLM 评估方式的局限性：

| 问题 | 本框架的方案 |
|------|------------|
| 所有任务用固定模板评分 | **动态评分标准** — 每步基于实际上下文生成针对性评分标准 |
| 只对最终答案二分法判对错 | **Process Reward** — 逐步骤评分，追踪错误传播路径 |
| 一次性评估，没有改进机制 | **自适应 Eval Loop** — 低分触发修正指令 → Agent 重试 → 重新评分 |
| 没有人参与决策 | **HITL 人工审批钩子** — 修正注入 / 重执行前可回调人工确认 |
| 手动判断是否需要重试 | **震荡检测** — 分数停滞时自动停止，避免无效循环 |

## 架构

```
src/eval_engine/
│
├── core/                        框架无关的核心评估原语
│   ├── contract.py              Verifier 契约接口（可组合评分标准）
│   ├── trajectory_parser.py     Agent 轨迹 → DAG 步骤结构
│   ├── dynamic_rubric.py        ★ 动态评分标准生成
│   └── process_reward.py        ★ 步骤级 Process Reward 评分 + 错误传播
│
├── judge/                       Judge LLM 调用
│   ├── executor.py              Judge LLM 封装（JSON 解析、重试、模板）
│   ├── template_loader.py       YAML 评分模板加载
│   ├── calibration.py           人机校准（κ / 一致率 / MAE / bias）
│   └── templates/               faithfulness.yaml / tool_selection.yaml /
│                                trajectory_safety.yaml
│
├── loop/                        自适应评估循环
│   ├── eval_loop.py             ★ 核心循环：评分 → 修正 → 重执行
│   └── fix_packer.py            修正指令打包
│
├── gates/                       评分门控
│   ├── baseline.py              BaselineManager 保存/对比
│   ├── regression_gate.py       回归检测
│   └── （运行产物写入用户状态目录，可用 EVAL_ENGINE_BASELINE_DIR 覆盖）
│
├── intent/                      任务分类路由
│   └── classifier.py            意图识别 → functional_test / generative_task
│
├── safety/                      人工审批
│   └── human_in_the_loop.py     HITL 回调接口
│
├── dataset/                     数据集管理
│   ├── manager.py               数据加载与拆分
│   └── data/                    golden.json + calibration_human_judge.json
│
└── observability/               可观测性
    └── report.py                审计报告生成
```

## 核心概念

### 1. 动态评分标准生成

不再对所有任务用同一份模板打分，而是基于每步的实际上下文动态生成评分标准：

```
Step 3（Agent 执行了 web_search 搜索 "Python SQL注入"）
→ 动态评分标准：
  ① 搜索词是否合理？
  ② 搜索结果是否被后续步骤利用？
  ③ 搜索效果不好时，Agent 是否有备选方案？
```

### 2. Process Reward 步骤级评分

受 o1/o3 Process Reward Model 启发——不只看最终答案，对每一步单独评分：

```
Step 1: web_search（得分: 0.92 ✅）
Step 2: read_results（得分: 0.85 ✅）
Step 3: review_tool（得分: 0.40 ❌ — 参数错误）
Step 4: summarize（得分: 0.60 ❌ — 基于不完整数据）
         ↑ 错误传播：Step 3 失败 → Step 4 受影响
```

### 3. 自适应 Eval Loop

```
Agent 执行 → 轨迹解析 → Process Reward 评分
       │                    │
       │               ┌────┴──────┐
       │            全部达标     有低分项
       │               │          │
       │               ▼          ▼
       │            输出结果   打包修正指令
       │               │          │
       │               │          ▼
       │               │    LLM 根据反馈重试
       │               │     → 再次进入循环
       └───────────────┘
```

- **最大迭代次数**：防止无限循环（默认 3）
- **最小改进幅度**：分数停滞时自动停止（震荡检测）
- **人工审批钩子**：修正注入和重执行前可设置 HITL 审批

## 快速开始

```bash
# 从源码安装（本地开发）
pip install -e .
# 或带测试依赖：pip install -e ".[test]"
```

```python
from eval_engine.loop.eval_loop import EvalLoopEngine, EvalLoopConfig

# 配置
config = EvalLoopConfig(max_iterations=3, verbose=True)

# 传入你的 Agent 执行函数和 Judge LLM 调用函数
engine = EvalLoopEngine(
    agent_fn=my_agent_run,     # Callable[[str], dict]
    judge_fn=my_judge_call,    # Callable[[str], dict]
    config=config,
)

# 执行
result = engine.execute("分析 Q3 财务报告")

if result.passed:
    print(result.final_output)
else:
    print(f"评分: {result.report.overall_score}")
    print(f"失败步骤: {result.report.error_sources}")
```

## 集成方式

框架与具体的 Agent 框架无关，你需要提供：

1. **agent_fn(query: str) -> dict** — Agent 执行函数，返回 `{"output": str, "trajectory": dict}`
2. **judge_fn(prompt: str) -> dict** — Judge LLM 调用函数，返回解析后的评分 JSON

### 人工审批

```python
from eval_engine.safety.human_in_the_loop import HumanInTheLoop

def ask_user(prompt, options):
    return input(f"{prompt} {options}: ")

hitl = HumanInTheLoop(ask_fn=ask_user)
engine = EvalLoopEngine(agent_fn=..., judge_fn=..., hitl=hitl)
```

## 测试

```bash
pip install -e ".[test]"
pytest tests/ -q
# 真实 Judge 集成测试（无 API Key 时自动 skip）
pytest tests/test_real_judge.py -v
```

## 环境要求

- Python 3.10+
- 核心模块纯 Python；Judge executor / YAML 模板为可选增强（`requests` 等）

## 与 react-agent 联动

轨迹可由 [react-agent](https://github.com/weihuaguo270-ops/react-agent) Harness 产出，再交给本仓库的 Process Reward / Eval Loop。

### 职责边界（避免双仓重复叙事）

| 仓 | 负责什么 | 不负责什么 |
|----|----------|------------|
| **react-agent `eval/`** | 任务 capability 规则打分、功能验证集、公开快照 | Process Reward / κ 校准 |
| **本仓 llm-eval-engine** | Process Reward、动态 rubric、人机校准、Eval Loop | Agent 运行时 / capability 数据集主维护 |

- **共享 Schema（Format B，1-based `step`）**：[react-agent/schemas/harness_trajectory.schema.json](https://github.com/weihuaguo270-ops/react-agent/blob/main/schemas/harness_trajectory.schema.json)
- **一键闭环**：`react-agent/examples/harness_closed_loop.py`（Agent → Trace Debugger → 本仓评分）
- **精简对接**：`react-agent/examples/agent_to_eval.py`

本仓库 `parse_trajectory` 会自动识别 1-based Format B；若轨迹仍用遗留 0-based `step`，也会兼容。

## 相关项目

- [react-agent](https://github.com/weihuaguo270-ops/react-agent) — ReAct Agent 学习实现
- [transformer-attention](https://github.com/weihuaguo270-ops/transformer-attention) — Attention 教学实现
- [trace-debugger](https://github.com/weihuaguo270-ops/trace-debugger) — 轨迹分析小工具

## CLI 工具

```bash
# 查看版本
python -m eval_engine version

# 评估轨迹文件
python -m eval_engine eval --query "问题" --trajectory trajectory.json

# 查看报告
python -m eval_engine report --file result.json
```

## 示例

```bash
python examples/quickstart.py
python examples/calibration_demo.py      # 合成多 Judge + 内置人机表
python examples/run_calibration.py       # 写出 docs/calibration_snapshot_*.md
python examples/run_calibration.py --live  # 可选：真实 Judge 重打分
```

## Judge 人机校准

目标：用小样本量化「人类标注 vs Judge」是否同刻度，而不是只打印合成 κ。

| 项 | 说明 |
|----|------|
| 数据 | [`calibration_human_judge.json`](src/eval_engine/dataset/data/calibration_human_judge.json)（**28** 条，**v3** = dev 17 + held_out 11） |
| 离线复现 | 冻结 `judge_score`；报告含 **dev/held_out 分栏** + bootstrap CI |
| 在线 | `--live` 调用 `JudgeExecutor`（注入刻度锚点） |
| 指标 | Cohen's κ、精确一致率、±1、MAE、Bias、混淆矩阵、**bootstrap 95% CI** |
| 怎么读 | [`docs/METRICS_TRUST.md`](docs/METRICS_TRUST.md) |
| 快照 offline | [`calibration_snapshot_20260716_offline.md`](docs/calibration_snapshot_20260716_offline.md) |
| 快照 live | [`calibration_snapshot_20260716_live.md`](docs/calibration_snapshot_20260716_live.md)（DeepSeek，v3 分栏） |

**offline v3：** 全量 κ≈**0.90**（CI [0.75, 1.0]）；**held_out** κ=**1.0**（n=11，冻结分）；dev κ≈0.84。第二标注者 **pending**。

**live v3（DeepSeek，2026-07-16 重跑）：** 全量 κ≈**0.68**（CI [0.45, 0.88]）；**held_out** κ≈**0.59**（n=11，CI [0.26, 1.0]，略低于 0.6 门禁 → `needs_calibration=是`）；dev κ≈0.73。

> 简历优先写 **held_out live κ + CI + n**，并注明单人标注。offline held_out=1.0 只证明冻结分对齐，不能当线上 SLA。

标注协议与 `meta.relabel_log` 写在数据文件中。HITL 人工审批（执行前确认）与本校准不是同一能力。

## 当前局限（诚实说明）

- 金标准 **28 条 v3**（dev/held_out）；小样本 + **单人标注**，第二标注者 pending
- offline held_out κ=1.0 基于冻结分，**不能**替代 live held_out
- HITL 审批 ≠ 人机校准
- 默认 CI 以离线单测为主；真实 Judge 需 API Key
- 与 react-agent `eval/` 分工：本仓 Process Reward / 校准；react-agent 任务通过率

## License

MIT

## 贡献与安全

见 [CONTRIBUTING.md](CONTRIBUTING.md) / [SECURITY.md](SECURITY.md)。
