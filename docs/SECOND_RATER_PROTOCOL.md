# 第二标注者协议（r2）

目标：在 **不伪造分数** 的前提下引入独立标注者，报告标注者间 κ，并支撑 held_out live 扩样。

## 角色

| 角色 | 字段 | 说明 |
|------|------|------|
| r1 | `human_score` | 仓库维护者；协议作者 |
| r2 | `human_score_r2` | 第二标注者；**不得**先看 r1 分或冻结 `judge_score` |
| Judge | `judge_score` / live | 模型分；与人工分独立 |

## 流程

1. 阅读本文件 + 数据文件 `meta.labeling_protocol`（刻度 1–5、边界裁决 v2 与灰区补全 v2.1）。
2. 打开 [`second_rater_worksheet.md`](second_rater_worksheet.md)，只看 `id` / `template` / `prompt`。
3. 独立打整数分；可写一行 `reason`。
4. 将分数回填到 `calibration_human_judge.json` 的 `human_score_r2`（或 PR 附 CSV，由维护者合并）。
5. 跑：

```bash
python examples/run_calibration.py
python examples/run_calibration.py --live   # 扩样后刷新 held_out live
```

报告出现 **标注者间 κ (r1 vs r2)** 后，才可引用「双人标注」结论。在此之前公开口径保持：`second_rater_status=protocol_ready`，**不报告双人 κ**。

## 禁止事项

- 对照 r1 / Judge 后再改自己的分（允许事后讨论，但初标必须盲评）
- 用模型生成「伪人工分」填入 `human_score_r2`
- 把 pending 条目（无 `human_score`）计入 κ

## 当前状态（v5；r2 已重标 2026-10-01）

- 协议与 worksheet：[`second_rater_worksheet.md`](second_rater_worksheet.md)
- held_out **n=53** 已全部写入新的 `human_score_r2`（盲标回填；二次修订）
- 标注者间 κ≈**0.72**（n=53，精确一致 81.1%，±1 一致 **100%**）
- held_out live κ≈**0.86**（n=53，CI [0.73, 0.97]，DeepSeek，2026-10-01；边界 v2.1）仍为「Judge vs r1」
  - 快照：[`calibration_snapshot_20261001_live_held_out.md`](calibration_snapshot_20261001_live_held_out.md)
- 旧双人 κ≈0.80（脚本伪 r2）已作废
