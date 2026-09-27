# 路线图

## 产品边界（2026-09-21）

| 层级 | 内容 |
|------|------|
| 主线 | 步骤级评测 → 失败归因 → 跨 Agent 发布判断 → 单一 release-audit |
| 多模态 | **轨迹上的一步**（工具 + ArtifactRef + 后续使用），走 Process Reward |
| 已删除 | 图像/视频选型流水线（横向对比、CLIP、图像 v2 / 视频自动门禁 `offline_real`） |

## P0

统一 **过程评测** evidence。入口：`examples/run_release_audit.py`。

- 主键：`episode` / `step` / `artifact`
- 多模态步维度：时机、参数忠实、产物使用、安全；门禁 `process_reward_media_steps_min`
- **可引用（钉死）**：held-out live κ≈0.70（n=40 **维单元格**，deepseek-chat，2026-09-22）；κ≈0.22 不当 SLA — [`CITATION_MULTIMODAL_PROCESS.md`](CITATION_MULTIMODAL_PROCESS.md)
- **κ 单位（钉死）**：多模态 = `dimension_cell` — [`METRICS_TRUST.md`](METRICS_TRUST.md)
- **扩样（分栏）**：expand **36**/312 cells κ≈0.62（CI [0.54, 0.69]）；业务 **12**；独立轨迹 ≈**48** — [`HELD_OUT_EXPAND.md`](HELD_OUT_EXPAND.md)
- **可谈未做**：可选 `human_score_r2`；加码对外「Judge 可信」（主钉仍分栏基线 0.70）
- **暂停**：签字 / shadow / 回滚——等业务流量入口和责任人
- **已删除**：图像/视频选型流水线与图像 v2 / 视频自动门禁 `offline_real`；主线只需轨迹内 generate/describe（含视频）过程评测

## P1

接入负责人签字、shadow 流量、在线告警与回滚演练（真实业务流量与责任人就绪后）
