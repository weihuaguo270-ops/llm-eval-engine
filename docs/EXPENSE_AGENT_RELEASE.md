# 报销 Agent 发布闭环

该流程把四个项目已有能力收束为一次可重复的业务发布演练：

```text
react-agent 运行基线与候选版本
  -> EvaluationEpisode v1
  -> 数据切分和泄漏审计
  -> 业务终态与过程规则验证
  -> 人工抽检记录
  -> trace-debugger 失败分布比较
  -> llm-inference-pipeline 性能证据
  -> pass / review / hold
  -> bad case 待处理队列
```

## 运行

四个仓库放在同一父目录，并安装 `react-agent`、`trace-debugger` 和
`llm-eval-engine`。从本仓执行：

```powershell
python examples/run_expense_release_pipeline.py `
  --out reports/expense-release/latest
```

验证阻断路径：

```powershell
python examples/run_expense_release_pipeline.py `
  --out reports/expense-release/fault-drill `
  --candidate-version expense-agent-broken `
  --candidate-profile no_action
```

正常路径退出码为 0；`review` 或 `hold` 返回非零，适合接入 CI。主要产物为
`release_report.json`、`dataset_audit.json`、`version_comparison.json`、
`failure_gate.json` 和 `feedback_queue.json`。

## 门禁口径

| 证据 | 规则 |
|---|---|
| 数据 | 必须存在 dev、golden、held_out，且不能跨 split 泄漏 |
| 业务终态 | 任一确定性状态断言失败即 hold |
| 版本比较 | 基线通过而候选失败即 hold |
| 过程质量 | 工具顺序不满足规则时进入 review |
| 人工抽检 | 覆盖不足进入 review，明确拒绝即 hold |
| 轨迹失败 | trace-debugger 相对基线的新增失败触发 review/hold |
| 性能 | 有证据时必须符合 `agent-release-evidence/v1` 且通过预算 |

反馈队列不会自动写回 golden。失败必须先完成归因、修复和人工确认，再提升为
回归样本，避免把环境故障或误报污染评测集。

## 证据边界

- 当前数据是版本化的仿真企业报销记录，不是任何公司的私有生产数据。
- 默认 Agent 是可重复的策略执行器，用来验证工具、副作用和门禁；不是远程模型质量证据。
- 仓库内人工复核文件是接口样例。真实发布必须替换为带日期和评审人的导出记录。
- CI 性能文件只验证接线；真实性能结论使用 `llm-inference-pipeline` 在指定设备生成的证据。
- 当前完成离线发布决策和反馈排队，未接生产流量、数据库、自动回滚或标注平台。
