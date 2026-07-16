# Judge 人机校准快照（20260716 / live）

- 样本量: **28**
- Cohen's κ: **0.6775**
- 精确一致率: **78.6%**
- ±1 分一致率: **96.4%**
- MAE: **0.25**
- Bias (Judge − Human): **0.1786**
- κ bootstrap 95% CI (seed=20260716, B=2000): **[0.4462, 0.8824]**
- 是否建议校准 (κ < 0.6): **是**
- 模式: `live`
- 说明: live 模式为当次 Judge 重打分；请同时看 held_out 分栏。

## 分栏（dev / held_out）

| split | n | κ | exact | ±1 | MAE |
|-------|--:|--:|------:|----:|----:|
| `dev` | 17 | 0.733 | 82.3% | 100.0% | 0.1765 |
| `held_out` | 11 | 0.5926 | 72.7% | 90.9% | 0.3636 |

- **held_out κ CI**: [0.2584, 1.0] （优先引用此栏，勿与 protocol-tuning 的 offline 全量 κ 混谈）

## 可复现元数据

- dataset_version: `3`
- rubric_boundary_version: `v2`
- annotator_count: `1`
- second_rater_status: `pending`
- judge_temperature_live: `0.1`
- random_seed_bootstrap: `20260716`
- mode: `live`

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 4 | 1 | 0 | 0 | 0 |
| 2 | 0 | 4 | 1 | 0 | 0 |
| 3 | 0 | 1 | 0 | 0 | 1 |
| 4 | 0 | 0 | 0 | 1 | 2 |
| 5 | 0 | 0 | 0 | 0 | 13 |

## 逐条对比

| id | split | human | judge | |err| |
|---|---|---:|---:|---:|
| cal_01 | dev | 5 | 5 | 0 |
| cal_02 | dev | 5 | 5 | 0 |
| cal_03 | dev | 2 | 3 | 1 |
| cal_04 | dev | 1 | 1 | 0 |
| cal_05 | dev | 5 | 5 | 0 |
| cal_06 | dev | 2 | 2 | 0 |
| cal_07 | dev | 1 | 1 | 0 |
| cal_08 | dev | 5 | 5 | 0 |
| cal_09 | dev | 5 | 5 | 0 |
| cal_10 | dev | 2 | 2 | 0 |
| cal_11 | dev | 5 | 5 | 0 |
| cal_12 | dev | 1 | 1 | 0 |
| cal_13 | dev | 4 | 5 | 1 |
| cal_14 | dev | 5 | 5 | 0 |
| cal_15 | dev | 4 | 5 | 1 |
| cal_16 | held_out | 5 | 5 | 0 |
| cal_17 | held_out | 2 | 2 | 0 |
| cal_18 | held_out | 5 | 5 | 0 |
| cal_19 | held_out | 5 | 5 | 0 |
| cal_20 | held_out | 2 | 2 | 0 |
| cal_21 | dev | 4 | 4 | 0 |
| cal_22 | held_out | 1 | 1 | 0 |
| cal_23 | held_out | 3 | 5 | 2 |
| cal_24 | held_out | 5 | 5 | 0 |
| cal_25 | held_out | 5 | 5 | 0 |
| cal_26 | held_out | 1 | 2 | 1 |
| cal_27 | held_out | 3 | 2 | 1 |
| cal_28 | dev | 5 | 5 | 0 |

## 金标准版本

- version: **3**
- updated: `2026-07-16`
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
