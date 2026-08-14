# 评测报告索引

本目录保存已冻结、可追溯的评测结果。运行脚本产生的临时报告应写入独立输出目录，不应直接
覆盖这些文件。

## 当前对外证据

| 文件 | 口径 |
|---|---|
| `benchmark_comparison_20260807.json` | 32×3 profile 的离线冻结分 |
| `benchmark_comparison_live_20260807.json` | 冻结轨迹使用 Live Judge 复评 |
| `benchmark_comparison_live_agent_20260807.json` | Live Agent 批量运行 |
| `calibration_report_20260807_live.json` | held-out Live Judge 校准 |
| `calibration_report_20260807_offline.json` | held-out 离线冻结 Judge 对照 |
| `calibration_report_20260807.json` | 2026-08-07 校准汇总 |

## 历史与兼容性记录

- `20260713`、`20260716`、`20260727` 报告用于展示校准和基准演进，不作为当前结论。
- `benchmark_comparison_agent_agent_20260727.json` 与
  `benchmark_comparison_agent_mock_20260727.json` 保留跨运行模式兼容性记录。
- `e2e_bench_tool_001_trajectory.json` 是端到端轨迹样例，不是批量评测结果。

删除或迁移历史文件前，应先检查 README、校准文档和 Release 是否仍引用该文件。当前报告与
历史报告必须分栏引用，不能只挑选最高分。

