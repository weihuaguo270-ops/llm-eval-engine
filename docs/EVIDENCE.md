# 证据摘要

## 可引用（钉死）

| 栏 | 值 |
|----|-----|
| 基线 held-out live κ | **≈0.70**（n=40 **维单元格** / 4 轨迹，deepseek-chat，2026-09-22） |
| κ 单位 | **`dimension_cell`** — [`METRICS_TRUST.md`](METRICS_TRUST.md) |
| 门禁 | `process_reward_media_steps_min` + 工具步 `media_arg_fidelity≤2`→review |
| 产物 | `reports/release_audit_live_four.json`、`reports/multimodal_held_out_live.json` |

**不当 SLA：** κ≈0.22；勿合成多栏总分。

## held_out_expand（分栏 · agreement_table + bootstrap）

| 项 | 值 |
|----|-----|
| 轨迹 / cells | **36** / **312** |
| live κ | ≈**0.62**（CI **[0.54, 0.69]**；更大 n 仍 ≥0.6） |
| 判定 | pass 15 / review 21 |
| 快照 | `docs/calibration_snapshot_20260922_live_held_out_multimodal_expand.md` |
| 产物 | `reports/release_audit_held_out_expand_live.json` |

## 真实业务（非 fixture，12 条）

2×ok→pass；10×坏→review（含 double-generate / 多余视频 / 空 prompt / uri-only）。报告：`reports/business_batch{2,3,4,5}_live.json` 等。

独立轨迹合计 ≈**48**（expand 36 + 业务 12）。

## r2 / 加码口径

κ 在更大 n 已 ≥0.6 → **可谈**可选 `human_score_r2` 与加码「Judge 可信」；**尚未执行**（无第二人则跳过 r2；对外主钉仍分栏引用基线 0.70）。

## 已删除（勿再引用）

图像与**视频选型流水线**（文生图/文生视频横向对比、CLIP 成对、图像 v2 / CogVideoX 等视频自动门禁 `offline_real`）——代码与文档入口已移除。

主线多模态只评轨迹内工具步：`generate_image` / `describe_image` / `generate_video` / `describe_video` → Process Reward → release-audit。另保留理解侧 VQA `offline_real`（非选型榜）。
