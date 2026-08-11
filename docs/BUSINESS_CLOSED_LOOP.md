# 离线评测与发布门禁原型

| 项目字段 | 当前值 |
|---|---|
| DRI | 郭伟华 |
| 状态 | 已完成离线原型 |
| 最近验证 | 2026-08-11 |
| 运行入口 | examples/run_business_closed_loop.py |
| 自动化测试 | tests/test_business_closed_loop.py |

## 当前流程

~~~text
固定评测样本
  -> 数据指纹和 split 审计
  -> Artifact 元数据与指标适配器
  -> 安全回归
  -> 基线漂移检查
  -> 离线发布结论
~~~

运行命令：

~~~bash
python examples/run_business_closed_loop.py
python examples/run_business_closed_loop.py --out reports/closed_loop.json
pytest tests/test_business_closed_loop.py
~~~

## 已实现

| 模块 | 实现位置 | 当前输出 |
|---|---|---|
| 数据版本 | src/eval_engine/dataset/governance.py | Manifest、Fingerprint、split 统计 |
| 数据审计 | src/eval_engine/dataset/governance.py | 重复 ID、语义重复、跨 split 泄漏 |
| 标注治理 | src/eval_engine/dataset/governance.py | 待标队列、一致性、仲裁结果 |
| Artifact 评测 | src/eval_engine/multimodal/evaluator.py | 元数据完整率、指标适配结果 |
| 安全回归 | src/eval_engine/safety/adversarial.py | ASR、良性通过率、违规项 |
| 漂移检查 | src/eval_engine/observability/drift.py | 整体和类别切片告警 |
| 发布检查 | src/eval_engine/observability/drift.py | 通过/阻断及证据摘要 |

内置 Artifact 指标只检查 URI 和技术元数据。CLIPScore、FID/FVD、VBench、
VLM Judge 和内容安全模型需要通过 MetricAdapter 接入。

## 尚未实现

| 能力 | 状态 | 前置条件 |
|---|---|---|
| 真实图片和视频指标 | 未接入 | 模型权重、真实数据、固定预处理 |
| 标注任务持久化 | 未实现 | 数据库和标注工作台 |
| Bad Case 自动回流 | 未实现 | 人工审批、Dataset 版本流程 |
| CI 发布阻断 | 未接入 | 目标仓库和发布策略 |
| 线上漂移监控 | 未实现 | Shadow 流量、时序存储、告警系统 |

因此当前结果只能作为离线代码路径和聚合逻辑的证据，不能作为真实媒体质量、
生产稳定性或线上发布闭环的证据。

## 变更要求

后续接入真实指标时，每次报告必须记录：

- Dataset 名称、版本、Fingerprint 和 split；
- 模型、Prompt、指标、阈值和预处理版本；
- 代码 Commit、依赖版本和运行设备；
- 自动指标、人工标签和 Judge 校准结果；
- 发布结论以及触发阻断的原始证据。
