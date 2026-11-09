# llm-eval-engine：发版前自检

llm-eval-engine 是企业内部工作助手（work-assistant）和规划中的受控变更交付（change-delivery）共用的发版前质量配件。它消费轨迹、业务终态和 trace-debugger 的 failure-gate，输出 pass / review / hold；不负责 Agent 运行时。

## 一句话定位

把工作助手或交付助手的过程、业务、失败和性能证据汇总成可复核的发版前自检结论。

## 做什么 / 不做什么

| 做什么 | 不做什么 |
|---|---|
| 步骤级 Process Reward、动态 rubric、Eval Loop | 不实现 Agent 运行时或权限闸门 |
| Judge 调用、人机校准、失败归因和数据切分审计 | 不替代 trace-debugger 的廉价规则失败检测 |
| 业务终态、失败门、质量/时延/成本证据汇总 | 不做生产监控、线上 SLA 或多租户评测 SaaS |
| 输出 pass / review / hold | 不把 offline κ、黄金集或模型比较写成生产指标 |

当前证据是离线、可复现的工程原型；工程交付证据来自 external_real_sandbox，不代表生产用户、真实流量或长期稳定性。

## 在工作助手闭环中的位置

~~~
工作助手或 change-delivery 产出轨迹
  → trace-debugger：规则失败打标、scan/compare、CI
  → llm-eval-engine：过程/业务证据与失败门
  → pass / review / hold
~~~

- react-agent / work-assistant：产生规范咨询、报销办理和受控执行轨迹。
- trace-debugger：提供便宜、确定、可回归的失败信号。
- llm-eval-engine：消费 failure-gate 与业务/过程证据，形成发版前自检结论。

两个质量仓保持独立，也可被 change-delivery 编排进 CI；不会合并成一个交付仓。

## 复现入口

~~~bash
pip install -e .
python -m eval_engine version
python -m eval_engine eval --query "问题" --trajectory trajectory.json
python examples/run_benchmark.py --compare
python examples/run_calibration.py --live --split held_out
python examples/run_cross_agent_release.py path/to/episodes --process-quality process.json --failure-gate failures.json --performance performance.json
~~~

共享 Format B / Episode 契约由 react-agent 维护；失败信号由 trace-debugger 维护。本仓只消费这些输入，不复制上游实现。

## 项目命名与边界

| 名称 | 角色 |
|---|---|
| 企业内部工作助手 / work-assistant | 主应用，负责规范咨询和报销办理 |
| 受控变更交付 / change-delivery | 规划中的独立应用，负责 Issue 到 Draft PR 的受控流程 |
| trace-debugger | 姊妹仓，轨迹失败雷达与 CI 钩子 |
| llm-eval-engine | 本仓，发版前自检并输出 pass/review/hold |

本仓不是独立评测 SaaS、生产监控平台或模型选型榜。

## 简历项目简介

为企业内部工作助手和受控变更交付构建发版前自检能力。
消费 Agent 轨迹、业务终态和 trace-debugger failure-gate，执行步骤级过程评测、失败归因和人机校准。
汇总质量、性能、业务和失败门证据，输出可复核的 pass、review 或 hold 结论。
支持固定 Benchmark、Eval Loop、数据切分审计和跨 Agent Episode，服务主应用而非替代运行时。
当前证据来自离线实验和 external_real_sandbox，不等同生产评测平台、线上 SLA 或多租户服务。

## 进一步阅读

- 当前状态：docs/STATUS.md
- 项目背景：docs/PROJECT_CONTEXT.md
- 跨仓分工：docs/POSITIONING_AND_DIVISION.md
- 业务与路线：docs/PROJECT_BUSINESS_DIRECTIONS_AND_GOALS.md
- 指标边界：docs/METRICS_TRUST.md
