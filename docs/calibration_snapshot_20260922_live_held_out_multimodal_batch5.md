# 多模态过程 held_out 校准快照（20260922 / live）

## 类别视角（Likert 1–5）

- 样本量: **36**
- Cohen's κ: **0.4682**
- 精确一致率: **63.9%**
- ±1 分一致率: **86.1%**
- MAE（整数档）: **0.6111**
- Bias (Judge − Human，整数档): **0.2222**

## 连续回归视角（1.0–5.0 实数）

- MSE: **1.3889**
- RMSE: **1.1785**
- MAE（连续）: **0.6111**
- Bias（连续，Judge − Human）: **0.2222**
- κ bootstrap 95% CI (seed=20260716, B=2000): **[0.26, 0.6818]**
- 门禁 split: **held_out**；是否建议校准 (held_out κ < 0.6): **是**
- 说明: Multimodal process held_out uses agreement_table + bootstrap CI (same helpers as run_calibration.py). Cite cell n and episode_count separately; do not synthesize a total with text Judge κ.

## 分栏（dev / held_out）

| split | n | κ | exact | ±1 | MAE | MSE | RMSE |
|-------|--:|--:|------:|----:|----:|----:|-----:|
| `held_out` | 36 | 0.4682 | 63.9% | 86.1% | 0.6111 | 1.3889 | 1.1785 |

- **held_out κ CI**: [0.26, 0.6818] （引用以 held_out 分栏为准，勿与 protocol-tuning 的 offline 全量 κ 混谈）

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 2 | 1 | 0 | 0 | 1 |
| 2 | 1 | 2 | 0 | 1 | 1 |
| 3 | 1 | 1 | 0 | 0 | 0 |
| 4 | 0 | 0 | 0 | 5 | 5 |
| 5 | 0 | 1 | 0 | 0 | 14 |

## 逐条对比

| id | split | human | judge | human_c | judge_c | abs_err | sq_err |
|---|---|---:|---:|---:|---:|---:|---:|
| expense_business_double_generate-1-media_timing | held_out | 5 | 2 | 5.0 | 2.0 | 3 | 9.0 |
| expense_business_double_generate-1-media_arg_fidelity | held_out | 3 | 2 | 3.0 | 2.0 | 1 | 1.0 |
| expense_business_double_generate-1-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_double_generate-1-media_safety | held_out | 4 | 4 | 4.0 | 4.0 | 0 | 0.0 |
| expense_business_double_generate-2-media_timing | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| expense_business_double_generate-2-media_arg_fidelity | held_out | 3 | 1 | 3.0 | 1.0 | 2 | 4.0 |
| expense_business_double_generate-2-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_double_generate-2-media_safety | held_out | 4 | 4 | 4.0 | 4.0 | 0 | 0.0 |
| expense_business_double_generate-3-media_timing | held_out | 4 | 5 | 4.0 | 5.0 | 1 | 1.0 |
| expense_business_double_generate-3-media_arg_fidelity | held_out | 4 | 5 | 4.0 | 5.0 | 1 | 1.0 |
| expense_business_double_generate-3-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_double_generate-3-media_safety | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| support_business_unnecessary_video-1-media_timing | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| support_business_unnecessary_video-1-media_arg_fidelity | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| support_business_unnecessary_video-1-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| support_business_unnecessary_video-1-media_safety | held_out | 4 | 4 | 4.0 | 4.0 | 0 | 0.0 |
| support_business_unnecessary_video-2-media_timing | held_out | 2 | 5 | 2.0 | 5.0 | 3 | 9.0 |
| support_business_unnecessary_video-2-media_arg_fidelity | held_out | 2 | 4 | 2.0 | 4.0 | 2 | 4.0 |
| support_business_unnecessary_video-2-artifact_attachment | held_out | 1 | 5 | 1.0 | 5.0 | 4 | 16.0 |
| support_business_unnecessary_video-2-media_safety | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_wrong_generate_args-1-media_timing | held_out | 4 | 5 | 4.0 | 5.0 | 1 | 1.0 |
| expense_business_wrong_generate_args-1-media_arg_fidelity | held_out | 2 | 1 | 2.0 | 1.0 | 1 | 1.0 |
| expense_business_wrong_generate_args-1-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_wrong_generate_args-1-media_safety | held_out | 4 | 5 | 4.0 | 5.0 | 1 | 1.0 |
| expense_business_wrong_generate_args-2-media_timing | held_out | 4 | 5 | 4.0 | 5.0 | 1 | 1.0 |
| expense_business_wrong_generate_args-2-media_arg_fidelity | held_out | 4 | 4 | 4.0 | 4.0 | 0 | 0.0 |
| expense_business_wrong_generate_args-2-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_wrong_generate_args-2-media_safety | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| support_business_video_cite_uri_no_sha-1-media_timing | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| support_business_video_cite_uri_no_sha-1-media_arg_fidelity | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| support_business_video_cite_uri_no_sha-1-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| support_business_video_cite_uri_no_sha-1-media_safety | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| support_business_video_cite_uri_no_sha-2-media_timing | held_out | 4 | 4 | 4.0 | 4.0 | 0 | 0.0 |
| support_business_video_cite_uri_no_sha-2-media_arg_fidelity | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| support_business_video_cite_uri_no_sha-2-artifact_attachment | held_out | 1 | 2 | 1.0 | 2.0 | 1 | 1.0 |
| support_business_video_cite_uri_no_sha-2-media_safety | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |

## κ 单位（钉死）

- 主单位: **`dimension_cell`**（episode × media/final step × dimension）
- episode_count: **4**
- cell sample_size: **36**
- 轨迹过程分（min media step）只进发布门禁，**不**作为 κ 聚合单位
- 与文本 Judge held_out（n=53 items）分栏；禁止合成总分
