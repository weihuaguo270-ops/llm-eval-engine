# 公开指标怎么读（可信度说明）

本项目对外发布指标时须**分栏引用**，不得合成一个「总分」。详见 [`EVAL_DESIGN.md`](EVAL_DESIGN.md)。

## 三栏对照

| 栏 | 含义 | 能不能当 SLA |
|----|------|--------------|
| **offline / frozen** | 冻结分数或注入故障；CI 可复现 | 否（证明机制/协议） |
| **mock** | 假 LLM / 假故障 | 否（冒烟） |
| **live** | 真实模型当次跑批 | 趋势证据；须绑定模型与日期 |
| **held_out**（Judge） | 协议冻结后的独立样本栏 | 对外发布优先于全量 offline |

## Judge κ（llm-eval-engine）

```bash
python examples/run_calibration.py          # offline + held_out 分栏 + bootstrap CI
python examples/run_calibration.py --live --split held_out   # 真实 Judge
```

- 金标准 **v5**：`dev`（协议调参）与 `held_out`（独立评估，n=53）分开；pending 条目不进 κ。
- 报告含 **bootstrap 95% CI**（seed 写在 `meta.reproducibility`）。
- **第二标注者**：v5 已写入 `human_score_r2`（n=53）；协议见 `SECOND_RATER_PROTOCOL.md`。

### 当前对外基准（v5，2026-07-27）

| 栏 | 值 | 说明 |
|----|-----|------|
| held_out **live** | κ≈**0.67**（n=53，CI [0.52, 0.82]，DeepSeek） | 对外 Judge 可信度主证据 |
| held_out **offline** | κ=**1.0**（n=53，冻结分） | 仅证明冻结 Judge 与 r1 对齐 |
| 标注者间 | κ≈**0.80**（n=53，r1 vs r2） | 金标准内部一致性 |
| 全量 offline | κ≈**0.96**（n=70） | 含 dev 协议调参样本，不作对外 SLA |

**废止口径：** n=15、κ≈0.47、held_out live n=20/κ≈0.69（v4 历史快照）、或「offline κ 当线上 SLA」。

## Execution 通过率（react-agent）

```bash
python examples/run_execution_suite.py --modes offline_tools
set REACT_AGENT_DISABLE_MCP=1
python examples/run_execution_suite.py --modes agent --publish
```

报告 `summary` 含：

- `pass_rate` / `task_completion_rate`
- `tool_success_rate` / `final_answer_rate`（分项，勿混谈）
- `pass_rate_wilson_95`（Wilson 区间）

复述通过率时须带样本量、模型与日期；点估计不能脱离上下文单独发布。

## Reliability

- 注入表：验证 Guard/自修机制
- live ON/OFF：看 **error_obs / tool_calls**，不要只看通过率

## 证据总图

见 [P0_EVIDENCE_MAP.md](https://github.com/weihuaguo270-ops/react-agent/blob/main/docs/P0_EVIDENCE_MAP.md)。
