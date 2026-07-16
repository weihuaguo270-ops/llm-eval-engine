# Judge 人机校准快照（20260716 / live）

- 样本量: **28**
- Cohen's κ: **0.6775**
- 精确一致率: **78.6%**
- ±1 分一致率: **96.4%**
- MAE: **0.25**
- Bias (Judge − Human): **0.1786**
- 是否建议校准 (κ < 0.6): **否**
- 模式: `live`
- 说明: live 模式为当次 Judge 重打分结果。

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 4 | 1 | 0 | 0 | 0 |
| 2 | 0 | 4 | 1 | 0 | 0 |
| 3 | 0 | 1 | 0 | 0 | 1 |
| 4 | 0 | 0 | 0 | 1 | 2 |
| 5 | 0 | 0 | 0 | 0 | 13 |

## 逐条对比

| id | human | judge | |err| |
|---|---:|---:|---:|
| cal_01 | 5 | 5 | 0 |
| cal_02 | 5 | 5 | 0 |
| cal_03 | 2 | 3 | 1 |
| cal_04 | 1 | 1 | 0 |
| cal_05 | 5 | 5 | 0 |
| cal_06 | 2 | 2 | 0 |
| cal_07 | 1 | 1 | 0 |
| cal_08 | 5 | 5 | 0 |
| cal_09 | 5 | 5 | 0 |
| cal_10 | 2 | 2 | 0 |
| cal_11 | 5 | 5 | 0 |
| cal_12 | 1 | 1 | 0 |
| cal_13 | 4 | 5 | 1 |
| cal_14 | 5 | 5 | 0 |
| cal_15 | 4 | 5 | 1 |
| cal_16 | 5 | 5 | 0 |
| cal_17 | 2 | 2 | 0 |
| cal_18 | 5 | 5 | 0 |
| cal_19 | 5 | 5 | 0 |
| cal_20 | 2 | 2 | 0 |
| cal_21 | 4 | 4 | 0 |
| cal_22 | 1 | 1 | 0 |
| cal_23 | 3 | 5 | 2 |
| cal_24 | 5 | 5 | 0 |
| cal_25 | 5 | 5 | 0 |
| cal_26 | 1 | 2 | 1 |
| cal_27 | 3 | 2 | 1 |
| cal_28 | 5 | 5 | 0 |

## 金标准版本

- version: **2**
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
