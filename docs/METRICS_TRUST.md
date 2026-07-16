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

- 金标准 **v4**：`dev`（协议调参）与 `held_out`（独立评估，已标 n=20）分开；pending 条目不进 κ。
- 报告含 **bootstrap 95% CI**（seed 写在 `meta.reproducibility`）。
- **第二标注者**：`protocol_ready`（见 `SECOND_RATER_PROTOCOL.md`）；`human_score_r2` 全为空 → **不报告双人 κ**。

### 当前应引用的唯一数字表

| 引用 | 值 |
|------|----|
| held_out **live** | κ≈**0.69**（n=20，CI [0.46, 0.92]，DeepSeek，门禁已过） |
| 全量 live | κ≈**0.67**（n=37，辅证） |
| held_out **offline** | κ=**1.0**（n=20，冻结分） |
| 全量 offline | κ≈**0.92**（n=37） |

**禁止**再写：n=15、κ≈0.47、held_out live n=11/κ≈0.59（扩容前快照）、或「offline κ 当线上 SLA」。

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
