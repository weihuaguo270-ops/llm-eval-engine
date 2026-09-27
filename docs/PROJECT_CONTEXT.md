# 项目背景

定位：LLM/Agent **发布前的过程评测与发布门禁**原型——步骤分、Eval Loop、失败归因、校准与跨 Agent 发布判断；不负责 Agent 运行时，也不是生成模型选型台。

边界：

- 不宣称线上 SLA、生产监控或训练型 PRM
- 多模态 = 轨迹上的工具步 + ArtifactRef + 过程分；生成侧选型（图像/视频横向榜）已删除
- 理解侧 VLM 可作步骤 Judge/检查器插件；理解 track `offline_real` 与生成选型无关
