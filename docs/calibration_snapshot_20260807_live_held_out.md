# Judge 人机校准快照（20260807 / live）

## 类别视角（Likert 1–5）

- 样本量: **53**
- Cohen's κ: **0.7294**
- 精确一致率: **83.0%**
- ±1 分一致率: **96.2%**
- MAE（整数档）: **0.2453**
- Bias (Judge − Human，整数档): **0.0943**

## 连续回归视角（1.0–5.0 实数）

- MSE: **0.5094**
- RMSE: **0.7137**
- MAE（连续）: **0.2453**
- Bias（连续，Judge − Human）: **0.0943**
- κ bootstrap 95% CI (seed=20260716, B=2000): **[0.5822, 0.879]**
- 门禁 split: **held_out**；是否建议校准 (held_out κ < 0.6): **否**
- 模式: `live`
- 说明: live 模式为当次 Judge 重打分；请同时看 held_out 分栏。
- 标注者间 κ (r1 vs r2, n=53): **0.7979**

## 分栏（dev / held_out）

| split | n | κ | exact | ±1 | MAE | MSE | RMSE |
|-------|--:|--:|------:|----:|----:|----:|-----:|
| `held_out` | 53 | 0.7294 | 83.0% | 96.2% | 0.2453 | 0.5094 | 0.7137 |

- **held_out κ CI**: [0.5822, 0.879] （引用以 held_out 分栏为准，勿与 protocol-tuning 的 offline 全量 κ 混谈）

## 可复现元数据

- dataset_version: `5`
- rubric_boundary_version: `v2`
- annotator_count: `2`
- second_rater_status: `completed_v5`
- judge_temperature_live: `0.1`
- random_seed_bootstrap: `20260716`
- mode: `live`

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 11 | 0 | 0 | 0 | 1 |
| 2 | 1 | 6 | 0 | 0 | 0 |
| 3 | 0 | 3 | 0 | 1 | 1 |
| 4 | 0 | 0 | 0 | 0 | 2 |
| 5 | 0 | 0 | 0 | 0 | 27 |

## 逐条对比

| id | split | human | judge | human_c | judge_c | abs_err | sq_err |
|---|---|---:|---:|---:|---:|---:|---:|
| cal_16 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_17 | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| cal_18 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_19 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_20 | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| cal_22 | held_out | 1 | 5 | 1.0 | 5.0 | 4 | 16.0 |
| cal_23 | held_out | 3 | 5 | 3.0 | 5.0 | 2 | 4.0 |
| cal_24 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_25 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_26 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_27 | held_out | 3 | 2 | 3.0 | 2.0 | 1 | 1.0 |
| cal_29 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_30 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_31 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_32 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_33 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_34 | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| cal_35 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_36 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_37 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_38 | held_out | 4 | 5 | 4.0 | 5.0 | 1 | 1.0 |
| cal_39 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_40 | held_out | 3 | 4 | 3.0 | 4.0 | 1 | 1.0 |
| cal_41 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_42 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_43 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_44 | held_out | 3 | 2 | 3.0 | 2.0 | 1 | 1.0 |
| cal_45 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_46 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_47 | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| cal_48 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_49 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_50 | held_out | 2 | 1 | 2.0 | 1.0 | 1 | 1.0 |
| cal_51 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_52 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_53 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_54 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_55 | held_out | 3 | 2 | 3.0 | 2.0 | 1 | 1.0 |
| cal_56 | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| cal_57 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_58 | held_out | 2 | 2 | 2.0 | 2.0 | 0 | 0.0 |
| cal_59 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_60 | held_out | 4 | 5 | 4.0 | 5.0 | 1 | 1.0 |
| cal_61 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_62 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_63 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_64 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_65 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_66 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_67 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_68 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |
| cal_69 | held_out | 5 | 5 | 5.0 | 5.0 | 0 | 0.0 |
| cal_70 | held_out | 1 | 1 | 1.0 | 1.0 | 0 | 0.0 |

## 金标准版本

- version: **5**
- updated: `2026-07-27`
- 本轮按协议重标边界样本: **6** 条（见数据文件 `meta.relabel_log`）

### 金标准内残留分歧（offline 冻结分，非本轮 live）

- `cal_21`: human=4 frozen_judge=3 — 残留分歧：近似表述是否扣到 3；协议倾向 4，冻结 Judge 偏严打 3
- `cal_28`: human=5 frozen_judge=4 — 残留分歧：NOTIFY 是否仍扣到 4；协议倾向 5，冻结 Judge 偏保守


## Live 接线

- wiring: `JUDGE_API_KEY<-DEEPSEEK_API_KEY, JUDGE_BASE_URL=deepseek, JUDGE_LLM_CONFIG=react-agent`
- model: `deepseek-chat`
- base_url: `https://api.deepseek.com`

## 如何复现

```bash
python examples/run_calibration.py          # offline
python examples/run_calibration.py --live   # 需 API Key
```

数据文件: `D:\agent_learning\llm-eval-engine\src\eval_engine\dataset\data\calibration_human_judge.json`
