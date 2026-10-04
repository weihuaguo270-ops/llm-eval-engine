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

held_out n=53 的 `human_score_r2` 已由独立第二标注者盲标回填（2026-10-01，标注者间 κ≈0.72，±1 一致 100%）；「加码对外 Judge 可信」仍未执行。对外按分栏引用：文本主钉 held_out live κ≈0.86，多模态主钉 ≈0.70，不合成总分。

## 结果判断（决策级 · 文本 Judge，2026-10-04）

| 项 | 值 |
|----|-----|
| 合格线出处 | `calibration_human_judge.json` → `meta.labeling_protocol` 刻度锚点（`verdict_bands_line1.json` 逐字留出处） |
| 缺陷率（human / judge） | **35.9% / 32.1%**（held_out n=53，live，item 级 95% CI [0.208, 0.453]） |
| **决策级一致率** | **96.2%**（51/53；与分数级 κ=0.8565 **并列不合成**） |
| 误杀 / 漏杀 | 0 / **2**（漏杀＝人判缺陷而 Judge 放过；均在 `tool_selection`） |
| 判据指纹 | `rubric_boundary_sha256 = 0a780f5ad7916440`（v2.1）；改判据未同步审计副本/未升版本即**测试失败** |
| 指标自验（注入缺陷） | 刻度**反向** κ→**0.4898**；删**全部**边界 −0.26；删**安全类**边界 −0.06~−0.09（均稳健检出）；删锚点/模糊材料**弱检出** ⇒ 小效应需**重复 ≥3 次** |

命令：`python examples/run_result_evaluation.py --split held_out`；口径见 [`EVAL_DESIGN.md`](EVAL_DESIGN.md) §3.2。

## 已删除（勿再引用）

图像与**视频选型流水线**（文生图/文生视频横向对比、CLIP 成对、图像 v2 / CogVideoX 等视频自动门禁 `offline_real`）——代码与文档入口已移除。

主线多模态只评轨迹内工具步：`generate_image` / `describe_image` / `generate_video` / `describe_video` → Process Reward → release-audit。另保留理解侧 VQA `offline_real`（非选型榜）。
