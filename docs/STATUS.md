# 项目状态

- 版本基线：v0.6.0（2026-10-04 结果判断（决策级）+ 判据指纹）
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
- **已完成（结果判断 · 决策级，2026-10-04）**：`examples/run_result_evaluation.py`；v2.1 held_out live 缺陷率 **35.9%（human）/ 32.1%（judge）**（item 级 CI [0.208, 0.453]）、**决策级一致率 96.2%**、误杀 0 / **漏杀 2**（均在 `tool_selection`）— [`EVAL_DESIGN.md`](EVAL_DESIGN.md) §3.2
- **已完成（判据指纹，2026-10-04）**：判据文本 `sha256[:16]=`**`0a780f5ad7916440`**（v2.1），写入报告 `reproducibility.rubric_boundary_sha256`；**改判据未同步审计副本/未升版本号即测试失败** — [`METRICS_TRUST.md`](METRICS_TRUST.md)
- **已完成（指标自验，2026-10-04）**：注入缺陷实验 7 变体 × 11 次 live——刻度**反向** κ 0.8565→**0.4898**（证明判据文本确实驱动 Judge）；删**全部**边界 **−0.26**、删**安全类**边界 **−0.06~−0.09** 均稳健检出；**删锚点/模糊材料为弱检出 ⇒ 小效应需重复 ≥3 次**
- **已完成（口径变体防护 + 预注册强制，2026-10-04）**：`judge/variant_ledger.py` 语义改为「**配额 = 每批一次 adopt 级对照**」（基线可重复跑不耗配额；配额内那次对照**必须先有预注册**，账本记其 sha256，冻结后被改动/删除即拒绝复现；第三个不同 adopt 指纹在**调用 Judge LLM 之前**拒绝）；端到端验证拒绝侧桩收到 **0** 次请求、放行侧确实收到请求 — [`EVAL_DESIGN.md`](EVAL_DESIGN.md) §3.3
- **负结果（2026-10-04）**：v2.1 → v2.1.1（补齐 3 条模板层已断言、`SCALE_ANCHORS` 缺失的条文）在同一批 held_out 上**未过采纳门槛**——三项统计量**配对置换 p 全为 1.0**，且 2 条变动**均属与改动无关** → **保留 v2.1（指纹 `0a780f5ad7916440` 逐字节不动）**；该批 adopt 配额**已用**，不得再在本批试第二个变体 — [`NEGATIVE_RESULTS.md`](NEGATIVE_RESULTS.md)
- **可谈但未做**：加码对外「Judge 可信」（主钉仍分栏引用 held_out live vs r1）
- **仍往后**：签字 / shadow / 回滚——等业务流量入口和责任人
- **已删除**：图像/视频选型流水线（横向对比、CLIP 成对、图像 v2 / 视频自动门禁 `offline_real`）；主线只保留轨迹内 `generate_video` / `describe_video`（及图像对）过程评测
- **已弃用（PR 记录）**：`cursor/multimodal-eval-gate-4fa3`（PR #5，2026-09-27 关闭未合并）的「媒体证据栏 + CLIP/safety 适配器」
  —— 与上一行同类：`ClipScoreMetric` 属被移出主线的生成类横向选型；归档于 tag `archive/cursor-multimodal-eval-gate-4fa3`（提交 `009d051`）及 PR #5 记录。
  其中两点如需复用：`SafetyClassifierMetric` 的 **fail-closed** 语义，以及「把媒体指标接成 `evaluate_evidence_bundle` 独立证据栏」的思路（现已有 `multimodal_understanding` 参数与 `MetricAdapter` 扩展点）。

