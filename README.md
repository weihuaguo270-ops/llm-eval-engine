# LLM Eval Engine

[![CI](https://github.com/weihuaguo270-ops/llm-eval-engine/actions/workflows/test.yml/badge.svg)](https://github.com/weihuaguo270-ops/llm-eval-engine/actions/workflows/test.yml) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Agent **过程级评测**仓库：把轨迹拆成步骤，用 Judge LLM 逐步打分（Process Reward），低分步可触发修正并重跑（Eval Loop）；另含固定 Benchmark、失败归因与人机校准。

> 术语：`Process Reward` 指本仓的过程级评分**流程**，不是训练好的 Process Reward Model（PRM），也不提供 PRM 训练数据或损失。

## 范围

| 做 | 不做 |
|----|------|
| 步骤级 Judge 打分 + 错误传播标注 | 训练型 PRM |
| 按上下文生成 rubric（`dynamic_rubric.py`） | 替代 react-agent 的 capability 主评测集 |
| Eval Loop：低分 → 修正 → 重跑（`eval_loop.py`） | Agent 运行时本身 |
| 人机校准：κ、MAE、MSE/RMSE、混淆矩阵 | 把 offline κ 当线上 SLA |
| 固定 Benchmark 跑批 + 多模型对比 | 端到端生产级 Agent 平台 |
| 失败类型 taxonomy + 分布统计 | 只报总分不做归因 |
| 回归门禁 + shipped baseline | 把 offline 对比当线上 SLA |

指标怎么采信、怎么对外引用，以 [`docs/EVAL_DESIGN.md`](docs/EVAL_DESIGN.md) 与 [`docs/METRICS_TRUST.md`](docs/METRICS_TRUST.md) 为准。

## 复现入口

| 能力 | 命令 | 备注 |
|------|------|------|
| Benchmark offline（32 条） | `python examples/run_benchmark.py` | CI 同款 |
| 回归门禁 | `python examples/run_benchmark.py --compare` | vs shipped baseline |
| Judge 校准 offline | `python examples/run_calibration.py` | v5，held_out n=53 |
| Live 校准 held_out | `python examples/run_calibration.py --live --split held_out` | 需 API Key |
| Live Judge 跑批 | `python examples/run_benchmark_live.py` | 需 API Key；轨迹冻结 |
| Live Agent 跑批 | `python examples/run_benchmark_agent.py --mode agent` | 需 react-agent + Key |
| E2E 轨迹评分 | `python examples/e2e_trajectory_eval.py` | 单条冒烟 |
| 设计 / 失败案例 | [`EVAL_DESIGN.md`](docs/EVAL_DESIGN.md) · [`failure_casebook.md`](docs/failure_casebook.md) | — |

## 当前证据（请分栏引用）

**Judge 校准**（金标准 v5；live 刷新 **2026-08-07**）：

| 栏 | 值 | 说明 |
|----|-----|------|
| held_out **live** | κ≈**0.73**（n=53，CI [0.58, 0.88]，DeepSeek） | 对外主证据 |
| held_out **offline** | κ=**1.0**（n=53，冻结分） | 仅证明冻结 Judge 与 r1 对齐 |
| 标注者间 | κ≈**0.80**（n=53，r1 vs r2） | 金标准内部一致性 |

快照：[`calibration_snapshot_20260807_live_held_out.md`](docs/calibration_snapshot_20260807_live_held_out.md) · [`_offline.md`](docs/calibration_snapshot_20260807_offline.md)

**Benchmark offline**（v2，32×3 profile）：

| 模型 profile | 通过率 | 均分 |
|-------------|-------:|-----:|
| deepseek-v3 | 100% | 4.90 |
| gpt-4o-mini | 72% | 3.80 |
| qwen-plus | 0% | 2.14 |

报告：[`benchmark_comparison_20260807.md`](docs/benchmark_comparison_20260807.md)

**Live Judge**（2026-08-07，冻结轨迹 × DeepSeek Judge，32×3）：

| 模型 profile | 通过率 | 均分 |
|-------------|-------:|-----:|
| deepseek-v3 | 46.9% | 4.24 |
| gpt-4o-mini | 40.6% | 3.70 |
| qwen-plus | 15.6% | 2.26 |

报告：[`benchmark_comparison_live_20260807.md`](docs/benchmark_comparison_live_20260807.md)（勿与 offline 冻结分混谈）

**Live Agent**（2026-08-07，react_loop + DeepSeek，32 条，Process Reward mock judge）：通过率 **100%**，均分 **4.00**（~11s/条）。报告：[`benchmark_comparison_live_agent_20260807.md`](docs/benchmark_comparison_live_agent_20260807.md)

## 架构

```
src/eval_engine/
├── core/                        框架无关的核心评估原语
│   ├── contract.py              Verifier 契约
│   ├── trajectory_parser.py     轨迹 → DAG
│   ├── dynamic_rubric.py        按步上下文生成评分标准
│   ├── process_reward.py        步骤级评分 + 错误传播
│   └── failure_taxonomy.py      低分步失败类型
├── benchmark/                   固定任务集跑批 + 对比报告
├── judge/                       Judge 调用、模板、人机校准
├── loop/                        评分 → 修正 → 重执行
├── gates/                       baseline / 回归门禁（含 shipped baseline）
├── intent/                      任务路由
├── safety/                      HITL 审批钩子
├── dataset/                     golden + calibration 数据
└── observability/               报告格式化
```

## 机制说明

### 动态 rubric

按当前步上下文生成评分维度，而不是全任务共用一张静态表。例如某步调用了 `web_search`，则可评搜索词是否合理、结果是否被后续利用、失败时有无备选。

### Process Reward

对每一步单独打分，并标错误传播（根因步权重大于下游受影响步）。`overall_score` 为步骤加权均分（根因步权 1.5），刻度 1–5。

### Eval Loop

```
Agent 执行 → 轨迹解析 → Process Reward
                 ├─ 达标 → 输出
                 └─ 低分 → 打包修正 → 重试（默认最多 3 轮，分数停滞则停）
```

修正注入与重执行前可挂 HITL。HITL ≠ 人机校准。

## 安装与最小用法

```bash
pip install -e .
# 或：pip install -e ".[test]"
```

```python
from eval_engine.loop.eval_loop import EvalLoopEngine, EvalLoopConfig

engine = EvalLoopEngine(
    agent_fn=my_agent_run,   # Callable[[str], dict] → {"output", "trajectory"}
    judge_fn=my_judge_call,  # Callable[[str], dict] → 评分 JSON
    config=EvalLoopConfig(max_iterations=3, verbose=True),
)
result = engine.execute("分析 Q3 财务报告")
```

框架与具体 Agent 实现解耦：你提供 `agent_fn` 与 `judge_fn` 即可。

## 测试与环境

```bash
pip install -e ".[test]"
pytest tests/ -q
pytest tests/test_real_judge.py -v   # 无 API Key 时 skip
```

- Python 3.10+
- 核心纯 Python；Judge HTTP / YAML 为可选增强（`requests` 等）

## 与 react-agent

轨迹可由 [react-agent](https://github.com/weihuaguo270-ops/react-agent) Harness 产出，再交本仓 Process Reward / Eval Loop。

| 仓 | 负责 | 不负责 |
|----|------|--------|
| **react-agent `eval/`** | 任务 capability、功能验证集、公开快照 | Process Reward / κ 校准 |
| **本仓** | Process Reward、动态 rubric、人机校准、过程级 Benchmark、Eval Loop | Agent 运行时 / capability 数据集主维护 |

- 共享 Schema（Format B，1-based `step`）：[harness_trajectory.schema.json](https://github.com/weihuaguo270-ops/react-agent/blob/main/schemas/harness_trajectory.schema.json)
- 闭环示例：`react-agent/examples/harness_closed_loop.py`、`agent_to_eval.py`
- 本仓 Agent 跑批：`python examples/run_benchmark_agent.py --mode mock|agent`

`parse_trajectory` 识别 1-based Format B，并兼容遗留 0-based `step`。

相关运行时： [react-agent](https://github.com/weihuaguo270-ops/react-agent)、[trace-debugger](https://github.com/weihuaguo270-ops/trace-debugger)。

## CLI 与示例

```bash
python -m eval_engine version
python -m eval_engine eval --query "问题" --trajectory trajectory.json
python -m eval_engine report --file result.json

python examples/quickstart.py
python examples/run_benchmark.py
python examples/run_benchmark.py --compare
python examples/run_benchmark_live.py
python examples/run_benchmark_agent.py --mode mock --max-cases 3
python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3
python examples/run_calibration.py
python examples/run_calibration.py --live --split held_out
python examples/e2e_trajectory_eval.py
```

## Judge 人机校准（摘要）

| 项 | 说明 |
|----|------|
| 数据 | [`calibration_human_judge.json`](src/eval_engine/dataset/data/calibration_human_judge.json)（v5：dev 17 + held_out 53 + r2） |
| 离线 | 冻结 `judge_score`；dev / held_out 分栏 + bootstrap CI |
| 在线 | `--live` → `JudgeExecutor` |
| 指标 | κ、精确一致、±1、MAE/Bias（整数档）、MSE/RMSE（连续 1.0–5.0）、混淆矩阵、标注者间 κ |
| 怎么读 | [`METRICS_TRUST.md`](docs/METRICS_TRUST.md) · [`SECOND_RATER_PROTOCOL.md`](docs/SECOND_RATER_PROTOCOL.md) |

历史快照（v4 / 2026-07 等）仅作对照，见 `docs/calibration_snapshot_202607*.md`。

## 已知局限

- Benchmark v2 为 curated 冻结样本（32 条），不是生产日志全量
- offline held_out κ=1.0 **不能**替代 live Judge
- offline 三模型 profile 是行为档位冻结轨迹，不是同一框架实时换 API 的大规模 live（live 脚本另跑并带日期）
- HITL 审批 ≠ 人机校准

## 数据治理与发布检查（原型）

当前实现：

- 数据集指纹、JSONL 读写、切分泄漏检查、双人标注一致性和仲裁；
- Artifact 元数据完整性检查和外部指标适配接口；
- 提示词注入、工具越权安全回归；
- 质量、时延、Token 成本漂移检查和离线发布结论。

运行：

~~~bash
python examples/run_business_closed_loop.py
pytest tests/test_business_closed_loop.py
~~~

示例使用固定 fixture 验证离线编排，不包含真实图片/视频指标、线上样本回流或 CI 发布阻断。
实现边界见 [docs/BUSINESS_CLOSED_LOOP.md](docs/BUSINESS_CLOSED_LOOP.md)，后续里程碑见
[docs/PROJECT_BUSINESS_DIRECTIONS_AND_GOALS.md](docs/PROJECT_BUSINESS_DIRECTIONS_AND_GOALS.md)。

## License / 贡献 / 安全

MIT · [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md)
