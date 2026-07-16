# Judge 人机校准快照（20260713）

> **历史基线**（v1，n=15，无 held-out）。当前口径见 [`calibration_snapshot_20260716_offline.md`](calibration_snapshot_20260716_offline.md) / [`_live.md`](calibration_snapshot_20260716_live.md) 与 [`METRICS_TRUST.md`](METRICS_TRUST.md)。**不要**把本页 κ≈0.47 当作当前结果。

- 样本量: **15**
- Cohen's κ: **0.4675**
- 精确一致率: **60.0%**
- ±1 分一致率: **100.0%**
- MAE: **0.4**
- Bias (Judge − Human): **0.1333**
- 是否建议校准 (κ < 0.6): **是**
- 模式: `offline`
- 说明: offline 使用数据集内冻结的 judge_score，便于 CI/复现；live 需配置 Judge API Key 后重打分。

## 混淆矩阵（行=Human，列=Judge）

| H\J | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 | 2 | 1 | 0 | 0 | 0 |
| 2 | 0 | 2 | 1 | 0 | 0 |
| 3 | 0 | 0 | 0 | 0 | 0 |
| 4 | 0 | 0 | 0 | 2 | 2 |
| 5 | 0 | 0 | 0 | 2 | 3 |

## 逐条对比

| id | human | judge | |err| |
|---|---:|---:|---:|
| cal_01 | 5 | 5 | 0 |
| cal_02 | 4 | 5 | 1 |
| cal_03 | 2 | 2 | 0 |
| cal_04 | 1 | 1 | 0 |
| cal_05 | 5 | 5 | 0 |
| cal_06 | 2 | 3 | 1 |
| cal_07 | 1 | 1 | 0 |
| cal_08 | 5 | 5 | 0 |
| cal_09 | 4 | 5 | 1 |
| cal_10 | 2 | 2 | 0 |
| cal_11 | 5 | 4 | 1 |
| cal_12 | 1 | 2 | 1 |
| cal_13 | 4 | 4 | 0 |
| cal_14 | 5 | 4 | 1 |
| cal_15 | 4 | 4 | 0 |

## 如何复现

```bash
python examples/run_calibration.py          # offline
python examples/run_calibration.py --live   # 需 API Key
```

数据文件: `D:\agent_learning\llm-eval-engine\src\eval_engine\dataset\data\calibration_human_judge.json`
