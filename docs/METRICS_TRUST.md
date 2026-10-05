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

### 有序量表口径（2026-10-04 新增 · **并列不替换**）

1–5 是**有序**量表。既有的 `cohens_kappa` 是**未加权**的（历史口径）；
标准统计是**加权 κ**（Cohen 1968）或 **Krippendorff α**。报告现已**并列**输出两者：

| 统计量 | 人机（held_out n=53，live） | 标注者间（r1 vs r2） |
|---|---|---|
| κ 未加权（**历史口径**） | 0.8565 | 0.7240 |
| **线性加权 κ** | **0.9483** | **0.8974** |
| 二次加权 κ | 0.9841 | 0.9679 |
| **Krippendorff α（ordinal）** | **0.9860** | **0.9499** |

- **为什么差这么多**：本批 held_out 的**全部分歧都是相邻档**（人机 5/5、人人 10/10 均为 `|差|=1`）。
  未加权 κ 把"1 vs 2"与"1 vs 5"同等计罚 → **系统性低估**一致性。
- **引用规则：必须带统计量与权重；四者不可混比，也不得用新口径替换历史数字。**
- 同时修正一处由此产生的误判：`trajectory_safety` 的「标注者间 κ=0.5556」是**未加权口径下的表象**，
  同口径下**线性加权 0.836 / α(ordinal) 0.942**（分歧同样全为相邻档）→ **不应据此判定"Rubric 不可执行"**。
- 实现：`src/eval_engine/judge/agreement.py`（`weighted_kappa` / `krippendorff_alpha` / `paired_permutation_kappa`）。
  **配对置换检验**用于**版本间**比较（例如 rubric 改动前后）——仅报 CI 无法回答"是否显著更差"。

## 结果判断（决策级 · 文本）

`κ` 只说分数一致性；**「能不能用」要看结果判断**。口径与命令见 [`EVAL_DESIGN.md`](EVAL_DESIGN.md) §3.2。

| 项 | 值（金标准 v5 · held_out n=53 · **live**） |
|----|------|
| 判定分布（human / judge） | pass 29/29｜marginal 5/7｜defect 19/17 |
| 缺陷率（human / judge） | 35.9% / 32.1%（item 级 95% CI **[0.208, 0.453]**） |
| **决策级一致率** | **96.2%**（51/53） |
| **误杀 / 漏杀** | 0 / **2**（漏杀＝人判缺陷而 Judge 放过；两处均在 `tool_selection`） |

- 与 κ **并列、不合成**：分数级 κ≈0.86 与决策级 96.2% 回答的是**不同问题**；
- **frozen 栏的结果判断不得引用**（只证复现一致）；
- Rubric 指纹 `reproducibility.rubric_boundary_sha256`（当前 v2.1 = `0a780f5ad7916440`）；
  改 Rubric 必须同步 `dataset/data/rubric_boundary_line1.json` 并升 `rubric_boundary_version`（有测试锁定）。

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

**r2 / 加码口径：** held_out n=53 的 `human_score_r2` 已由独立第二标注者盲标回填（2026-10-01，标注者间 κ≈0.72，±1 一致 100%）；「加码对外 Judge 可信」仍未执行。对外按分栏引用：文本主钉 held_out live κ≈0.86（边界 v2.1），多模态主钉 ≈0.70（`dimension_cell`），不合成总分。

## 姊妹仓：Execution 通过率（react-agent）

任务通过率不在本仓维护。见 [react-agent](https://github.com/weihuaguo270-ops/react-agent) 的 execution suite 与证据图 [P0_EVIDENCE_MAP.md](https://github.com/weihuaguo270-ops/react-agent/blob/main/docs/P0_EVIDENCE_MAP.md)。复述时须带样本量、模型与日期。

## Reliability（react-agent）

- 注入表：验证 Guard/自修
- live ON/OFF：看 **error_obs / tool_calls**，不要只看通过率
