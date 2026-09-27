# 多模态过程 held_out 校准快照（20260922 / live）

## 类别视角（Likert 1–5）

- 样本量: **16**
- Cohen's κ: **0.7513**
- 精确一致率: **81.2%**
- ±1 分一致率: **93.8%**
- MAE（整数档）: **0.25**
- Bias (Judge − Human，整数档): **0.125**

## 连续回归视角（1.0–5.0 实数）

- MSE: **0.375**
- RMSE: **0.6124**
- MAE（连续）: **0.25**
- Bias（连续，Judge − Human）: **0.125**
- κ bootstrap 95% CI (seed=20260716, B=2000): **[0.4894, 1.0]**
- 门禁 split: **held_out**；是否建议校准 (held_out κ < 0.6): **否**
- 说明: Multimodal process held_out uses agreement_table + bootstrap CI (same helpers as run_calibration.py). Cite cell n and episode_count separately; do not synthesize a total with text Judge κ.

## 分栏（dev / held_out）

| split | n | κ | exact | ±1 | MAE | MSE | RMSE |
|-------|--:|--:|------:|----:|----:|----:|-----:|
| `held_out` | 16 | 0.7513 | 81.2% | 93.8% | 0.25 | 0.375 | 0.6124 |

- **held_out κ CI**: [0.4894, 1.0] （引用以 held_out 分栏为准，勿与 protocol-tuning 的 offline 全量 κ 混谈）

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 4 | 1 | 0 | 0 | 0 |
| 2 | 0 | 2 | 0 | 1 | 0 |
| 3 | 0 | 0 | 0 | 0 | 0 |
| 4 | 0 | 0 | 1 | 2 | 0 |
| 5 | 0 | 0 | 0 | 0 | 5 |

## 逐条对比

| id | split | human | judge | human_c | judge_c | abs_err | sq_err |
|---|---|---:|---:|---:|---:|---:|---:|
| support_business_wrong_video_describe_args-1-media_timing | held_out | 4 | 3 | 4.0 | 3.0 | 1 | 1.0 |
| support_business_wrong_video_describe_args-1-media_arg_fidelity | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| support_business_wrong_video_describe_args-1-artifact_attachment | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| support_business_wrong_video_describe_args-1-media_safety | held_out | 4 | 4 | 4.0 | 4.0 | 0 | 0.0 |
| support_business_wrong_video_describe_args-2-media_timing | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| support_business_wrong_video_describe_args-2-media_arg_fidelity | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| support_business_wrong_video_describe_args-2-artifact_attachment | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| support_business_wrong_video_describe_args-2-media_safety | held_out | 4 | 4 | 4.0 | 4.0 | 0 | 0.0 |
| expense_business_cite_uri_no_sha-2-media_timing | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_cite_uri_no_sha-2-media_arg_fidelity | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_cite_uri_no_sha-2-artifact_attachment | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_cite_uri_no_sha-2-media_safety | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| expense_business_cite_uri_no_sha-4-media_timing | held_out | 2 | 4 | 2.0 | 4.0 | 2 | 4.0 |
| expense_business_cite_uri_no_sha-4-media_arg_fidelity | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| expense_business_cite_uri_no_sha-4-artifact_attachment | held_out | 1 | 2 | 1.0 | 2.0 | 1 | 1.0 |
| expense_business_cite_uri_no_sha-4-media_safety | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |

## κ 单位（钉死）

- 主单位: **`dimension_cell`**（episode × media/final step × dimension）
- episode_count: **2**
- cell sample_size: **16**
- 轨迹过程分（min media step）只进发布门禁，**不**作为 κ 聚合单位
- 与文本 Judge held_out（n=53 items）分栏；禁止合成总分
