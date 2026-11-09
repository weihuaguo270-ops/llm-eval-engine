# 项目背景与对外边界

llm-eval-engine 是企业内部工作助手（work-assistant）和规划中的受控变更交付（change-delivery）的发版前自检配件。

## 负责什么

- 消费工作助手或交付助手产生的 Format B / Episode 轨迹。
- 通过 trace-debugger 的 failure-gate、业务终态、过程评分和性能证据做发版前自检。
- 输出 pass、review 或 hold，并保留数据、Rubric、Judge 和报告版本信息。

## 不负责什么

- 不负责 Agent 运行时、工具权限、人工审批或业务应用本身。
- 不替代 trace-debugger 的规则失败检测和 scan/compare。
- 不宣称生产监控、线上 SLA、多租户平台或独立评测 SaaS。
- 不把 offline κ、黄金集数量或模型比较写成生产结论。

## 跨仓闭环

~~~
工作助手或 change-delivery 产出轨迹
  → trace-debugger：失败打标、scan/compare、CI
  → llm-eval-engine：过程/业务证据与失败门
  → pass / review / hold
~~~

当前代码和文档保留离线与 external_real_sandbox 证据边界；真实业务责任人、线上告警和回滚仍是后续条件。
