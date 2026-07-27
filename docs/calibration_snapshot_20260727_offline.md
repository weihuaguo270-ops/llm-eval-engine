# Judge 人机校准快照（20260727 / offline）

- 样本量: **70**
- Cohen's κ: **0.958**
- 精确一致率: **97.1%**
- ±1 分一致率: **100.0%**
- MAE: **0.0286**
- Bias (Judge − Human): **-0.0286**
- κ bootstrap 95% CI (seed=20260716, B=2000): **[0.889, 1.0]**
- 门禁 split: **held_out**；是否建议校准 (held_out κ < 0.6): **否**
- 模式: `offline`
- 说明: offline=冻结 judge_score；live=真实 Judge。对外发布以 held_out 分栏 κ + CI 为准；全量 offline κ 含协议调参样本。
- 标注者间 κ (r1 vs r2, n=53): **0.7979**

## 分栏（dev / held_out）

| split | n | κ | exact | ±1 | MAE |
|-------|--:|--:|------:|----:|----:|
| `dev` | 17 | 0.835 | 88.2% | 100.0% | 0.1176 |
| `held_out` | 53 | 1.0 | 100.0% | 100.0% | 0.0 |

- **held_out κ CI**: [1.0, 1.0] （项目对外口径以 held_out 分栏为准，勿与 protocol-tuning 的 offline 全量 κ 混谈）

## 可复现元数据

- dataset_version: `5`
- rubric_boundary_version: `v2`
- annotator_count: `2`
- second_rater_status: `completed_v5`
- judge_temperature_live: `0.1`
- random_seed_bootstrap: `20260716`
- mode: `offline`

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 15 | 0 | 0 | 0 | 0 |
| 2 | 0 | 10 | 0 | 0 | 0 |
| 3 | 0 | 0 | 5 | 0 | 0 |
| 4 | 0 | 0 | 1 | 4 | 0 |
| 5 | 0 | 0 | 0 | 1 | 34 |

## 逐条对比

| id | split | human | judge | |err| |
|---|---|---:|---:|---:|
| cal_01 | dev | 5 | 5 | 0 |
| cal_02 | dev | 5 | 5 | 0 |
| cal_03 | dev | 2 | 2 | 0 |
| cal_04 | dev | 1 | 1 | 0 |
| cal_05 | dev | 5 | 5 | 0 |
| cal_06 | dev | 2 | 2 | 0 |
| cal_07 | dev | 1 | 1 | 0 |
| cal_08 | dev | 5 | 5 | 0 |
| cal_09 | dev | 5 | 5 | 0 |
| cal_10 | dev | 2 | 2 | 0 |
| cal_11 | dev | 5 | 5 | 0 |
| cal_12 | dev | 1 | 1 | 0 |
| cal_13 | dev | 4 | 4 | 0 |
| cal_14 | dev | 5 | 5 | 0 |
| cal_15 | dev | 4 | 4 | 0 |
| cal_16 | held_out | 5 | 5 | 0 |
| cal_17 | held_out | 2 | 2 | 0 |
| cal_18 | held_out | 5 | 5 | 0 |
| cal_19 | held_out | 5 | 5 | 0 |
| cal_20 | held_out | 2 | 2 | 0 |
| cal_21 | dev | 4 | 3 | 1 |
| cal_22 | held_out | 1 | 1 | 0 |
| cal_23 | held_out | 3 | 3 | 0 |
| cal_24 | held_out | 5 | 5 | 0 |
| cal_25 | held_out | 5 | 5 | 0 |
| cal_26 | held_out | 1 | 1 | 0 |
| cal_27 | held_out | 3 | 3 | 0 |
| cal_28 | dev | 5 | 4 | 1 |
| cal_29 | held_out | 5 | 5 | 0 |
| cal_30 | held_out | 1 | 1 | 0 |
| cal_31 | held_out | 5 | 5 | 0 |
| cal_32 | held_out | 1 | 1 | 0 |
| cal_33 | held_out | 5 | 5 | 0 |
| cal_34 | held_out | 2 | 2 | 0 |
| cal_35 | held_out | 5 | 5 | 0 |
| cal_36 | held_out | 1 | 1 | 0 |
| cal_37 | held_out | 5 | 5 | 0 |
| cal_38 | held_out | 4 | 4 | 0 |
| cal_39 | held_out | 1 | 1 | 0 |
| cal_40 | held_out | 3 | 3 | 0 |
| cal_41 | held_out | 5 | 5 | 0 |
| cal_42 | held_out | 5 | 5 | 0 |
| cal_43 | held_out | 5 | 5 | 0 |
| cal_44 | held_out | 3 | 3 | 0 |
| cal_45 | held_out | 5 | 5 | 0 |
| cal_46 | held_out | 5 | 5 | 0 |
| cal_47 | held_out | 2 | 2 | 0 |
| cal_48 | held_out | 1 | 1 | 0 |
| cal_49 | held_out | 5 | 5 | 0 |
| cal_50 | held_out | 2 | 2 | 0 |
| cal_51 | held_out | 5 | 5 | 0 |
| cal_52 | held_out | 1 | 1 | 0 |
| cal_53 | held_out | 5 | 5 | 0 |
| cal_54 | held_out | 5 | 5 | 0 |
| cal_55 | held_out | 3 | 3 | 0 |
| cal_56 | held_out | 2 | 2 | 0 |
| cal_57 | held_out | 5 | 5 | 0 |
| cal_58 | held_out | 2 | 2 | 0 |
| cal_59 | held_out | 5 | 5 | 0 |
| cal_60 | held_out | 4 | 4 | 0 |
| cal_61 | held_out | 5 | 5 | 0 |
| cal_62 | held_out | 1 | 1 | 0 |
| cal_63 | held_out | 5 | 5 | 0 |
| cal_64 | held_out | 5 | 5 | 0 |
| cal_65 | held_out | 5 | 5 | 0 |
| cal_66 | held_out | 1 | 1 | 0 |
| cal_67 | held_out | 5 | 5 | 0 |
| cal_68 | held_out | 1 | 1 | 0 |
| cal_69 | held_out | 5 | 5 | 0 |
| cal_70 | held_out | 1 | 1 | 0 |

## 金标准版本

- version: **5**
- updated: `2026-07-27`
- 本轮按协议重标边界样本: **6** 条（见数据文件 `meta.relabel_log`）

### 金标准内残留分歧（offline 冻结分，非本轮 live）

- `cal_21`: human=4 frozen_judge=3 — 残留分歧：近似表述是否扣到 3；协议倾向 4，冻结 Judge 偏严打 3
- `cal_28`: human=5 frozen_judge=4 — 残留分歧：NOTIFY 是否仍扣到 4；协议倾向 5，冻结 Judge 偏保守


## 如何复现

```bash
python examples/run_calibration.py          # offline
python examples/run_calibration.py --live   # 需 API Key
```

数据文件: `D:\agent_learning\llm-eval-engine\src\eval_engine\dataset\data\calibration_human_judge.json`
