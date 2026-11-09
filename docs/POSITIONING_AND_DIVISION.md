# 跨仓定位与分工

本文固定企业内部工作助手、受控变更交付和两个质量配件的职责边界。

## 一句话分工

| 项目 | 一句话定位 |
|---|---|
| work-assistant / react-agent | 企业内部工作助手，办理规范咨询和报销办理并产出轨迹 |
| change-delivery | 规划中的独立受控变更交付，读取 Issue、影子执行、审批后创建 Draft PR |
| trace-debugger | 轨迹失败雷达与 CI 钩子，输出确定性失败证据 |
| llm-eval-engine | 发版前自检，汇总过程/业务证据并输出 pass/review/hold |

## 推荐闭环

~~~
工作助手或受控变更交付产出轨迹
  → trace-debugger：规则失败打标、scan/compare、CI
  → llm-eval-engine：过程/业务证据与失败门
  → pass / review / hold
~~~

## 交接边界

| 产物 | 生产者 | 消费者 |
|---|---|---|
| Format B 轨迹 / Episode | work-assistant 或 change-delivery | 两个质量仓 |
| failures / findings / failure-gate | trace-debugger | llm-eval-engine |
| Process / business / release 报告 | llm-eval-engine | 负责人和 CI |

## 做 / 不做

本仓做步骤级 Process Reward、动态 Rubric、Eval Loop、Judge 校准、业务/失败/性能证据汇总和 pass/review/hold。

本仓不做 Agent 运行时、权限闸门、业务应用、tdebug 规则失败检测、生产监控、线上 SLA、多租户平台或独立评测 SaaS。

change-delivery 当前只在文档中规划，代码仍留在 react-agent；它不复制权限、轨迹或审批实现。

## 命名与简历边界

对外先讲 work-assistant 应用，再讲本仓的发版前自检角色。κ、黄金集数量、模型比较和离线门禁只作为验收证据。

简历项目简介：

为企业内部工作助手和受控变更交付构建发版前自检能力。
消费 Agent 轨迹、业务终态和 trace-debugger failure-gate，执行步骤级过程评测、失败归因和人机校准。
汇总质量、性能、业务和失败门证据，输出可复核的 pass、review 或 hold 结论。
支持固定 Benchmark、Eval Loop、数据切分审计和跨 Agent Episode，服务主应用而非替代运行时。
当前证据来自离线实验和 external_real_sandbox，不等同生产评测平台、线上 SLA 或多租户服务。
