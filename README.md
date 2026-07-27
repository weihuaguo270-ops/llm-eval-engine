# LLM Eval Engine

[![CI](https://github.com/weihuaguo270-ops/llm-eval-engine/actions/workflows/test.yml/badge.svg)](https://github.com/weihuaguo270-ops/llm-eval-engine/actions/workflows/test.yml) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

本项目是 Agent **过程级评测引擎**：将轨迹拆成步骤，用 Judge LLM 逐步打分（Process Reward），低分步可触发修正并重跑（Eval Loop）；并提供固定 Benchmark、失败归因与人机校准（κ）。

> 术语：`Process Reward` 在这里指 Judge LLM 的过程级评分**流程**，不是训练出来的 Process Reward Model（PRM），也不提供 PRM 训练数据或损失函数。

## 本仓库做什么 / 不做什么

| 做 | 不做 |
|----|------|
| 步骤级 Judge 打分 + 错误传播标注 | 训练型 PRM |
| 按上下文生成 rubric（`dynamic_rubric.py`） | 替代 react-agent 的 capability 主评测集 |
| Eval Loop：低分 → 修正 → 重跑（`eval_loop.py`） | Agent 运行时本身 |
| 人机校准：κ、MAE、混淆矩阵（`calibration.py`） | 把 offline κ 当线上 SLA |
| **固定 Benchmark 跑批 + 多模型对比报告** | 端到端生产级 Agent 平台 |
| **失败类型 taxonomy + 分布统计** | 只报总分不做归因 |
| **回归门禁 + shipped baseline** | 把 offline 对比当线上 SLA |

和「固定 rubric 打总分」相比，这里多四件事：**逐步打分**、**低分触发重跑**、**可复现的模型对比结论**、**失败归因统计**。

## 项目交付物

| 优先级 | 产物 | 复现命令 | 状态 |
|--------|------|----------|------|
| P0 | Benchmark **32 条** | `python examples/run_benchmark.py` | ✅ |
| P0 | Eval 设计文档 | [`docs/EVAL_DESIGN.md`](docs/EVAL_DESIGN.md) | ✅ |
| P0 | Judge 校准 v5 | `python examples/run_calibration.py` | ✅ held_out n=53 |
| P0 | Live Judge 跑批 | `python examples/run_benchmark_live.py` | 🔧 需 API Key |
| P0 | Live 校准 held_out | `python examples/run_calibration.py --live --split held_out` | 🔧 需 API Key |
| P1 | 失败案例库 | [`docs/failure_casebook.md`](docs/failure_casebook.md) | ✅ |
| P1 | CI 回归门禁 | [`.github/workflows/benchmark.yml`](.github/workflows/benchmark.yml) | ✅ |
| P0 | Live Agent 跑批 | `run_benchmark_agent.py --mode agent` | ✅ n=32 DeepSeek |

**Live Agent 结论（2026-07-27，react_loop + DeepSeek，32 条）：**

| 指标 | 结果 |
|------|------|
| 通过率 | **100%**（32/32，Process Reward mock judge） |
| 均分 | 4.00 |
| 平均延迟 | ~40s/条 |
| vs offline 冻结 | agent 4.00 vs offline 4.90（轨迹为真实 Agent 产出） |

报告：[`docs/benchmark_comparison_agent_agent_20260727.md`](docs/benchmark_comparison_agent_agent_20260727.md)

**当前 Benchmark 结论（offline v2，32 条 × 3 profile）：**

| 模型 profile | 通过率 | 均分 |
|-------------|-------:|-----:|
| deepseek-v3 | 100% | 4.90 |
| gpt-4o-mini | 72% | 3.80 |
| qwen-plus | 0% | 2.14 |

> 指标口径与对外发布规范见 [`docs/EVAL_DESIGN.md`](docs/EVAL_DESIGN.md)

## 架构

```
src/eval_engine/
│
├── core/                        框架无关的核心评估原语
│   ├── contract.py              Verifier 契约接口（可组合评分标准）
│   ├── trajectory_parser.py     Agent 轨迹 → DAG 步骤结构
│   ├── dynamic_rubric.py        ★ 动态评分标准生成
│   ├── process_reward.py        ★ 步骤级 Process Reward 评分 + 错误传播
│   └── failure_taxonomy.py      ★ 低分步骤失败类型归类
│
├── benchmark/                   ★ 固定任务集跑批 + 多模型对比
│   ├── runner.py
│   └── report.py
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
│       baselines/benchmark_baseline.json  ★ 仓库随附 shipped baseline
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
- **Benchmark Agent 跑批**（本仓）：`python examples/run_benchmark_agent.py --mode mock|agent`

本仓库 `parse_trajectory` 会自动识别 1-based Format B；若轨迹仍用遗留 0-based `step`，也会兼容。

## 相关项目

- [react-agent](https://github.com/weihuaguo270-ops/react-agent) — Agent 运行时 + 证据化文档排障（轨迹由 Harness 产出）
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
python examples/run_benchmark.py              # Benchmark v2（32 条）
python examples/run_benchmark_live.py         # Live Judge（需 Key）
python examples/run_benchmark.py --compare    # 回归门禁
python examples/e2e_trajectory_eval.py        # 轨迹→评分 E2E
python examples/run_benchmark_agent.py --mode mock --max-cases 3   # react-agent 集成
python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3  # live Agent
python examples/run_calibration.py            # 校准 v5
python examples/run_calibration.py --live --split held_out  # Live held_out
```

## Judge 人机校准

目标：用小样本量化「人类标注 vs Judge」是否同刻度，而不是只打印合成 κ。

| 项 | 说明 |
|----|------|
| 数据 | [`calibration_human_judge.json`](src/eval_engine/dataset/data/calibration_human_judge.json)（**v5**：dev 17 + held_out **53** + r2 已写入） |
| 离线复现 | 冻结 `judge_score`；**dev/held_out 分栏** + bootstrap CI；跳过 pending |
| 在线 | `--live` 调用 `JudgeExecutor`（注入刻度锚点） |
| 指标 | Cohen's κ、精确一致率、±1、MAE、Bias、混淆矩阵、**bootstrap 95% CI**；held_out 报告 **标注者间 κ**（r1 vs r2） |
| 怎么读 | [`docs/METRICS_TRUST.md`](docs/METRICS_TRUST.md) · [第二标注者](docs/SECOND_RATER_PROTOCOL.md) |
| 快照 offline | [`calibration_snapshot_20260716_offline.md`](docs/calibration_snapshot_20260716_offline.md)（v4） |
| 快照 live | [`calibration_snapshot_20260716_live.md`](docs/calibration_snapshot_20260716_live.md)（DeepSeek，**v4** held_out n=20） |

**统一口径（v5 offline，2026-07-27）：**

| 栏 | 数字 | 说明 |
|----|------|------|
| **held_out offline**（对外基准） | κ=**1.0**（n=53，冻结分） | 只证明冻结 Judge 与 r1 对齐 |
| **标注者间** | κ≈**0.80**（n=53，r1 vs r2） | v5 第二标注者已写入 |
| 全量 offline | κ≈**0.96**（n=70） | 含 dev 协议调参样本 |
| held_out **live**（历史） | κ≈**0.69**（n=20，DeepSeek） | 需 `--live` 复跑；样本小于 v5 |

> 旧基线 v4（n=20 held_out）与 `calibration_snapshot_20260713` 仅作历史对照。

标注协议与 `meta.relabel_log` 写在数据文件中。HITL 人工审批（执行前确认）与本校准不是同一能力。

## 当前局限

- 金标准 **v5**（held_out n=53 + r2）；Benchmark **v2** 共 **32 条**（5 类各 ≥6）
- offline held_out κ=1.0 基于冻结分，**不能**替代 live Judge 复跑
- Benchmark 三模型 profile 使用**冻结轨迹 + 冻结 Judge 分**，非实时 API 跑批（`--live` 可扩展）
- HITL 审批 ≠ 人机校准
- 与 react-agent `eval/` 分工：本仓 Process Reward / 校准 / 过程级 benchmark；react-agent 任务通过率

## License

MIT

## 贡献与安全

见 [CONTRIBUTING.md](CONTRIBUTING.md) / [SECURITY.md](SECURITY.md)。
