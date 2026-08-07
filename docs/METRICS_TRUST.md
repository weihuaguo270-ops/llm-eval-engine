# 公开指标怎么读

本仓数字须**分栏引用**（offline / live / held_out / mock），不得合成「总分」。设计口径见 [`EVAL_DESIGN.md`](EVAL_DESIGN.md)。

## 三栏对照

| 栏 | 含义 | 能否当 SLA |
|----|------|------------|
| **offline / frozen** | 冻结分数或注入故障；CI 可复现 | 否（验证机制/协议） |
| **mock** | 假 LLM / 假故障 | 否（冒烟） |
| **live** | 真实模型当次跑批 | 趋势证据；须绑定模型与日期 |
| **held_out**（Judge） | 协议冻结后的独立样本栏 | 对外引用优先于全量 offline |

## Judge κ（本仓）

```bash
python examples/run_calibration.py          # offline + held_out 分栏 + bootstrap CI
python examples/run_calibration.py --live --split held_out   # 真实 Judge
```

- 金标准 **v5**：`dev`（协议调参）与 `held_out`（独立评估，n=53）分开；pending 不进 κ。
- 报告含 **bootstrap 95% CI**（seed 见 `meta.reproducibility`）。
- **第二标注者**：v5 已写入 `human_score_r2`（n=53）；协议见 `SECOND_RATER_PROTOCOL.md`。
- **双视角**：Likert κ / 精确一致看档位；**MSE / RMSE / 连续 MAE** 看 1.0–5.0 幅度（`EVAL_DESIGN.md` §3.1）。

### 当前基准（v5；live 刷新 2026-08-07）

| 栏 | 值 | 说明 |
|----|-----|------|
| held_out **live** | κ≈**0.73**（n=53，CI [0.58, 0.88]，DeepSeek） | Judge 可信度主证据 |
| held_out **offline** | κ=**1.0**（n=53，冻结分） | 仅证明冻结 Judge 与 r1 对齐 |
| 标注者间 | κ≈**0.80**（n=53，r1 vs r2） | 金标准内部一致性 |
| 全量 offline | κ≈**0.96**（n=70） | 含 dev 调参样本，不作 SLA |

快照：[`calibration_snapshot_20260807_live_held_out.md`](calibration_snapshot_20260807_live_held_out.md)

**废止口径：** n=15、κ≈0.47；held_out live n=20/κ≈0.69（v4）；held_out live κ≈0.67（2026-07-27）；或「offline κ 当线上 SLA」。

## 姊妹仓：Execution 通过率（react-agent）

任务通过率不在本仓维护。见 [react-agent](https://github.com/weihuaguo270-ops/react-agent) 的 execution suite 与证据图 [P0_EVIDENCE_MAP.md](https://github.com/weihuaguo270-ops/react-agent/blob/main/docs/P0_EVIDENCE_MAP.md)。复述时须带样本量、模型与日期。

## Reliability（react-agent）

- 注入表：验证 Guard/自修
- live ON/OFF：看 **error_obs / tool_calls**，不要只看通过率
