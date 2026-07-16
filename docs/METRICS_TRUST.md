# 公开指标怎么读（可信度说明）

面试/简历请**分栏引用**，不要合成一个「总分」。

## 三栏对照

| 栏 | 含义 | 能不能当 SLA |
|----|------|--------------|
| **offline / frozen** | 冻结分数或注入故障；CI 可复现 | 否（证明机制/协议） |
| **mock** | 假 LLM / 假故障 | 否（冒烟） |
| **live** | 真实模型当次跑批 | 趋势证据；绑定模型与日期 |
| **held_out**（Judge） | 协议冻结后的独立样本栏 | 比全量 offline 更适合写简历 |

## Judge κ（llm-eval-engine）

```bash
python examples/run_calibration.py          # offline + held_out 分栏 + bootstrap CI
python examples/run_calibration.py --live   # 真实 Judge
```

- 金标准 **v3**：`dev`（协议调参/重标）与 `held_out`（独立评估）分开。
- 报告含 **bootstrap 95% CI**（seed 写在 `meta.reproducibility`）。
- **第二标注者**：`second_rater.status=pending`（当前仅 r1，不假装有双人 κ）。

优先引用：**held_out live κ + CI**，并注明 n、模型与单人标注。

**2026-07-16 live（DeepSeek）：** held_out κ≈**0.59**（n=11，CI [0.26, 1.0]）；全量 κ≈**0.68**。held_out 略低于门禁 0.6，报告诚实标 `needs_calibration`；区间很宽，小样本下勿夸成稳定 SLA。

## Execution 通过率（react-agent）

```bash
python examples/run_execution_suite.py --modes offline_tools
set REACT_AGENT_DISABLE_MCP=1
python examples/run_execution_suite.py --modes agent --publish
```

报告 `summary` 现含：

- `pass_rate` / `task_completion_rate`
- `tool_success_rate` / `final_answer_rate`（分项，勿混谈）
- `pass_rate_wilson_95`（Wilson 区间）

**36/36** 是某次 live 快照点估计；复述时请带样本量、模型与「学习级」边界。

## Reliability

- 注入表：证明 Guard/自修机制  
- live ON/OFF：看 **error_obs / tool_calls**，不要只看通过率  

## 证据总图

见 [P0_EVIDENCE_MAP.md](https://github.com/weihuaguo270-ops/react-agent/blob/main/docs/P0_EVIDENCE_MAP.md)。
