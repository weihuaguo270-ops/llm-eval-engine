# 可引用口径（多模态过程审计 · 钉死）

> 更新：2026-09-22。主线已立住「真 Judge + 可引用 κ + 对的 pass/review」。

## 对外只引这些

| 项 | 口径 |
|----|------|
| Judge | `deepseek-chat`（`JudgeExecutor` / DeepSeek API） |
| held-out live κ | **≈0.70**（n=40 **维单元格**，4 条轨迹，2026-09-22） |
| κ 单位 | **`dimension_cell`**（非轨迹聚合）— [`METRICS_TRUST.md`](METRICS_TRUST.md) |
| 过程判定 | ok / video-ok → **pass**；多余出图 / 终态未引用 → **review** |
| 门禁指标 | `process_reward_media_steps_min`（最弱媒体步；步内仍为四维平均） |
| 证据产物 | `reports/release_audit_live_four.json` + `reports/multimodal_held_out_live.json` |

## 明确不当 SLA

- **κ≈0.22**：旧 human × 首轮 live Judge 的**过渡数**，只作重标对照，**不得对外当 SLA**。
- 当前 κ 来自 **4 条 fixture 轨迹**；方差大，扩样前勿写成「Judge 生产 SLA」。
- 文本侧 held_out live κ≈0.73（n=53）是**另一套**金标准，勿与多模态四维混引为同一 SLA。
- 签字 / shadow / 回滚、生成榜、CLIP 主结论：**未就绪**，不引用。

## 分栏扩样（勿与基线合成总分）

| 栏 | 口径 |
|----|------|
| held_out_expand | **36** 轨迹 / **312** cells；κ≈**0.62**（CI [0.54, 0.69]） |
| 业务（非 fixture） | **12** 条：2×ok→pass；10×坏→review |
| 独立轨迹合计 | ≈**48**（近文本 held_out ≈53） |
| 统计形态 | `agreement_table` + bootstrap CI（与 `run_calibration.py` 同形） |

更大 n 上 κ 仍 ≥0.6 → **可谈**可选 r2 / 加码「Judge 可信」；**尚未执行**。签字 / shadow / CLIP：**未就绪**。

扩样操作说明见 [`HELD_OUT_EXPAND.md`](HELD_OUT_EXPAND.md)。
