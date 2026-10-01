# 公开指标怎么读

本仓数字须**分栏引用**（offline / live / held_out / mock），不得合成「总分」。设计口径见 [`EVAL_DESIGN.md`](EVAL_DESIGN.md)。

## 三栏对照

| 栏 | 含义 | 能否当 SLA |
|----|------|------------|
| **offline / frozen** | 冻结分数或注入故障；CI 可复现 | 否（验证机制/协议） |
| **mock** | 假 LLM / 假故障 | 否（冒烟） |
| **live** | 真实模型当次跑批 | 趋势证据；须绑定模型与日期 |
| **held_out**（Judge） | 协议冻结后的独立样本栏 | 对外引用优先于全量 offline |

## Judge κ（本仓 · 文本）

```bash
python examples/run_calibration.py          # offline + held_out 分栏 + bootstrap CI
python examples/run_calibration.py --live --split held_out   # 真实 Judge
```

- 金标准 **v5**：`dev`（协议调参）与 `held_out`（独立评估，n=53）分开；pending 不进 κ。
- **边界协议**：`rubric_boundary_version=v2.1`（v2 + 灰区补全；固化既有标注惯例）。
- **κ 单位（文本）**：按校准 **item**（一条 prompt 的 overall `human_score`↔`judge_score`）。
- 报告含 **agreement_table + bootstrap 95% CI**（seed 见 `meta.reproducibility`）。
- **第二标注者**：v5 held_out **n=53** 已重标写入 `human_score_r2`（2026-10-01 盲标）；协议见 `SECOND_RATER_PROTOCOL.md`。
- **双视角**：Likert κ / 精确一致看档位；**MSE / RMSE / 连续 MAE** 看 1.0–5.0 幅度（`EVAL_DESIGN.md` §3.1）。

### 当前基准（v5；live 刷新 2026-10-01 · 边界 v2.1）

| 栏 | 值 | 说明 |
|----|-----|------|
| held_out **live** | κ≈**0.86**（n=53，CI [0.73, 0.97]，DeepSeek，精确一致 90.6%） | Judge 可信度主证据（vs r1） |
| held_out **offline** | κ=**1.0**（n=53，冻结分） | 仅证明冻结 Judge 与 r1 对齐 |
| 标注者间 | κ≈**0.72**（n=53，r1 vs r2；精确一致 81.1%，±1 **100%**） | 金标准内部一致性（二次修订后） |
| 全量 offline | κ≈**0.96**（n=70） | 含 dev 调参样本，不作 SLA |

快照：[`calibration_snapshot_20261001_live_held_out.md`](calibration_snapshot_20261001_live_held_out.md)

**废止口径：** n=15、κ≈0.47；held_out live n=20/κ≈0.69（v4）；held_out live κ≈0.67（2026-07-27）；held_out live κ≈0.73（2026-08-07，边界 v2）；或「offline κ 当线上 SLA」。

## 多模态过程审计（release-audit · κ 单位钉死）

与上表文本 Judge 金标准**分栏**，勿合成同一 SLA。完整口径：[`CITATION_MULTIMODAL_PROCESS.md`](CITATION_MULTIMODAL_PROCESS.md)。

### κ 单位（钉死 · 不可改口径）

| 项 | 规定 |
|----|------|
| **主单位** | **`dimension_cell`**：`episode × media/final step × dimension` |
| **不是** | 按轨迹聚合的过程分（min media step）——该分只进 **发布门禁**，不进 κ |
| **并列报告** | `sample_size` = cell n；`episode_count` = 独立轨迹数（样本广度，非 κ 分母） |
| **统计形态** | 与 `run_calibration.py` 相同：`agreement_table` + `bootstrap_ci` + `by_split.held_out` |
| **CLI** | `run_release_audit.py --calibration-md …` 写出同形态 markdown 快照 |

```bash
python examples/run_release_audit.py examples/fixtures/episodes/held_out_expand \
  --live --calibration … --rebuild-calibration … \
  --out reports/release_audit_held_out_expand_live.json \
  --calibration-md docs/calibration_snapshot_YYYYMMDD_live_held_out_multimodal_expand.md
```

### 当前分栏数字（2026-09-22）

| 栏 | 轨迹 | cell n | κ | bootstrap 95% CI | 说明 |
|----|------|--------|---|------------------|------|
| 基线 fixture | 4 | 40 | ≈**0.70** | — | 对外主钉 |
| held_out_expand | **36** | **312** | ≈**0.62** | **[0.54, 0.69]** | 更大 n 仍 ≥0.6 |
| 业务（非 fixture） | **12** | 分批 | 分条 gate | — | ok→pass / 坏→review |

独立轨迹合计 ≈**48**（近文本 held_out ≈53）。

**过渡数（不当 SLA）：** κ≈0.22 = 旧 human × 首轮 live Judge。

**r2 / 加码口径：** κ 在更大 n 已 ≥0.6 → 可谈可选 `human_score_r2` 与加码「Judge 可信」；**尚未执行**（无第二人则跳过；主钉仍分栏引用基线 0.70）。

## 姊妹仓：Execution 通过率（react-agent）

任务通过率不在本仓维护。见 [react-agent](https://github.com/weihuaguo270-ops/react-agent) 的 execution suite 与证据图 [P0_EVIDENCE_MAP.md](https://github.com/weihuaguo270-ops/react-agent/blob/main/docs/P0_EVIDENCE_MAP.md)。复述时须带样本量、模型与日期。

## Reliability（react-agent）

- 注入表：验证 Guard/自修
- live ON/OFF：看 **error_obs / tool_calls**，不要只看通过率
