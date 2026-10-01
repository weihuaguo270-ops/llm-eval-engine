# 项目状态

- 版本基线：v0.5.1（2026-09 multimodal offline_real 增量）
- **可引用口径（钉死）**：[`CITATION_MULTIMODAL_PROCESS.md`](CITATION_MULTIMODAL_PROCESS.md)
  - 基线 4 轨迹 κ≈**0.70**（n=40 **维单元格**）；κ≈0.22 不当 SLA
- **κ 单位（钉死）**：多模态 = **`dimension_cell`** — [`METRICS_TRUST.md`](METRICS_TRUST.md)
- **分栏证据（勿合成总分）**
  | 栏 | 轨迹 | cells | κ | CI | 说明 |
  |----|------|-------|---|----|------|
  | 基线 fixture | 4 | 40 | ≈0.70 | — | 对外主钉 |
  | held_out_expand | **36** | **312** | ≈**0.62** | [0.54, 0.69] | 更大 n 仍 ≥0.6 |
  | 业务（非 fixture） | **12** | 分批 | 分条 gate | — | 2×pass / 10×review |
- **独立轨迹合计 ≈48**（近文本 held_out ≈53）
- **已完成（文本 r2）**：held_out 53 条 `human_score_r2` 盲标回填；标注者间 κ≈0.72（±1 一致 100%）
- **可谈但未做**：加码对外「Judge 可信」（主钉仍分栏引用 held_out live vs r1）
- **仍往后**：签字 / shadow / 回滚——等业务流量入口和责任人
- **已删除**：图像/视频选型流水线（横向对比、CLIP 成对、图像 v2 / 视频自动门禁 `offline_real`）；主线只保留轨迹内 `generate_video` / `describe_video`（及图像对）过程评测
- **已弃用（PR 记录）**：`cursor/multimodal-eval-gate-4fa3`（PR #5，2026-09-27 关闭未合并）的「媒体证据栏 + CLIP/safety 适配器」
  —— 与上一行同类：`ClipScoreMetric` 属被移出主线的生成类横向选型；归档于 tag `archive/cursor-multimodal-eval-gate-4fa3`（提交 `009d051`）及 PR #5 记录。
  其中两点如需复用：`SafetyClassifierMetric` 的 **fail-closed** 语义，以及「把媒体指标接成 `evaluate_evidence_bundle` 独立证据栏」的思路（现已有 `multimodal_understanding` 参数与 `MetricAdapter` 扩展点）。

