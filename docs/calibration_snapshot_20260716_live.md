# Judge 人机校准快照（20260716 / live）

- 样本量: **37**
- Cohen's κ: **0.6682**
- 精确一致率: **78.4%**
- ±1 分一致率: **97.3%**
- MAE: **0.2432**
- Bias (Judge − Human): **0.1892**
- κ bootstrap 95% CI (seed=20260716, B=2000): **[0.4762, 0.8518]**
- 门禁 split: **held_out**；是否建议校准 (held_out κ < 0.6): **否**
- 模式: `live`
- 说明: live 模式为当次 Judge 重打分；请同时看 held_out 分栏。
- 标注者间 κ: **未报告**（第二标注者尚未写入 `human_score_r2`）

## 分栏（dev / held_out）

| split | n | κ | exact | ±1 | MAE |
|-------|--:|--:|------:|----:|----:|
| `dev` | 17 | 0.644 | 76.5% | 100.0% | 0.2353 |
| `held_out` | 20 | 0.6887 | 80.0% | 95.0% | 0.25 |

- **held_out κ CI**: [0.4576, 0.9222] （优先引用此栏，勿与 protocol-tuning 的 offline 全量 κ 混谈）

## 可复现元数据

- dataset_version: `4`
- rubric_boundary_version: `v2`
- annotator_count: `1`
- second_rater_status: `protocol_ready`
- judge_temperature_live: `0.1`
- random_seed_bootstrap: `20260716`
- mode: `live`

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 5 | 3 | 0 | 0 | 0 |
| 2 | 0 | 5 | 1 | 0 | 0 |
| 3 | 0 | 1 | 0 | 0 | 1 |
| 4 | 0 | 0 | 0 | 1 | 2 |
| 5 | 0 | 0 | 0 | 0 | 18 |

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
| cal_12 | dev | 1 | 2 | 1 |
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
| cal_29 | held_out | 5 | 5 | 0 |
| cal_30 | held_out | 1 | 1 | 0 |
| cal_31 | held_out | 5 | 5 | 0 |
| cal_32 | held_out | 1 | 1 | 0 |
| cal_33 | held_out | 5 | 5 | 0 |
| cal_34 | held_out | 2 | 2 | 0 |
| cal_35 | held_out | 5 | 5 | 0 |
| cal_36 | held_out | 1 | 2 | 1 |
| cal_37 | held_out | 5 | 5 | 0 |

## 金标准版本

- version: **4**
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
