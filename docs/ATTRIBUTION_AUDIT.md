# 归因审计（Attribution Audit）

**审计对象：** `ProcessRewardScorer` → `report.error_sources`（根因步）→ release audit 这条链路。
**方法：** 静态代码审计 + 42 个 episode 夹具实测（默认夹具模式）；**未跑 live**。
**日期：** 2026-09-30 · 对应 PR：llm-eval-engine #8、trace-debugger #8。

## 摘要（一句话）

`error_sources` 由 **Judge 语义分 + DAG 拓扑**合成，而审计前**没有任何东西检验它是否与确定性事实一致**；同时评分与归因在"分数缺失"这件事上有 **2 态而需要 3 态**，导致大量**假根因**。本审计修掉同族缺陷并接入了第一道可机器执行的校验。

---

## 1. 已修（本审计期间）

| # | 问题 | 实测影响 | 修复 |
|---|------|----------|------|
| 1 | **阈值分裂**：根因定位用 `find_error_sources()` 默认阈值 **3.0**，`needs_revision` 用 `min_step_score` **3.5** | 落在 [3.0, 3.5) 的失败步"要修却永不可能是根因" | 两处调用点改传 `threshold=self.min_step_score`（`core/process_reward.py`） |
| 2 | **未评估态缺失**：缺失 `step_score` 回退中性 **3**（< 阈值）→ 没评过被读成失败 | 42 夹具中 **40/42** 报出 `error_sources`（假根因） | 显式未评估：`step_score=0`、`node.score=None`（`None = 未评` 本就是 `StepNode` 的约定） |
| 3 | **编造中性分**：媒体/终态步无评分证据时被赋 `context=3.0`（judge 侧，非 scorer） | 同上；根因全是"没评过的步" | `judge_multimodal_step` 不再编造；保留保守的 `needs_revision=True` 但**不给分** |
| 4 | **三态缺"不适用"**：思考步携带 `context` 值——**全仓无任何评分口径**——且被加权进 `report.overall_score` | 与 `HELD_OUT_EXPAND.md:29`「思考步不进过程分」矛盾；实测 `num_scored=3=num_steps` | `StepScore.applicable`；不适用步不计分、不触发修订、不进总分 |
| 5 | **taxonomy 误标**：未评估步被归类为 `error_propagation`（"下游受影响"） | 写进对外 failure taxonomy | 新增 `unscored` 类型；未评估步不再算作根因或下游 |
| 6 | **fast 模式缺省当 0**：`_score_fast` 用 `get(key, 0)` 平均 `overall/efficiency/tool_usage` | 逐步型 Judge（dimension judge）在 fast 模式恒得 **0 分**；`eval_loop` 对 `num_steps < 5` 走 fast。此前 **fast 模式零测试覆盖** | 只对**真正给出**的维度取均值；一个都没有 → 未评估 |
| 7 | **rubric 缺分伪造 3** | 3 < 阈值 → 读成失败；且会漏进 `_score_episode` 的媒体维度聚合 | 无分数的 rubric 跳过而非伪造 |
| 8 | **judge_error 被吞**：第 5 项引入的早返回把所有无分步标 `unscored`，Judge 崩溃不再走 `"Judge 异常"` 匹配 | 崩溃与"没评"混为一谈 | 先查 rubric reason / `role_understanding`，再决定 `judge_error` 或 `unscored` |
| 9 | **`None` 被强转 0.0**：`evidence_bundle` 用 `float(... or 0.0)` | 未评分被报成 `process score 0.000 below 3.500`（假低分） | 显式区分 missing 与真实 0 分 |
| 10 | **锚点校验未接线**：`attribution_anchor` 模块只被测试调用 | 无度量 | 审计报告新增 `attribution_anchors` 块（**只写报告、不参与决策**；trace-debugger 缺失时记 `skipped`） |
| 11 | **（跨仓）盲表 provenance 泄漏**：trace-debugger 的 `build_sheet` 带 `source_file`，`case_id` 取自文件名 | 夹具文件名即失败类型名（`search_empty.json`）→ 标注者直接读到答案，破坏盲评前提 | 盲表用不透明 `case_id`、不含来源；provenance 只在 key（trace-debugger #8 `27db844`） |
| 12 | **（跨仓）媒体规则孤岛**：trace-debugger 的 `analyze_multimodal_steps`（精确规则：空 prompt / 缺 path / sha 不匹配 / 终态未引用 / NSFW）**只被测试调用**；审计走 `adapt_media_rule_findings(metadata.trace_analysis)`，而该上游当前**不产出**那 4 个媒体类型 | 报告里"媒体规则证据"几乎恒空——**覆盖假象** | 未修（见 §2 待决策） |

### 修复后的实测（42 个 episode 夹具，夹具模式）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 报出 `error_sources` 的 episode | **40 / 42** | **2 / 42** |
| `needs_revision` 的 episode | 40 | **40（不变）** |
| 门禁/决策分布 | 40 review / 2 pass | **40 review / 2 pass（不变）** |
| `num_scored == 0` 的 episode | 0 | **38 / 42**（诚实暴露"没评过"） |
| `mm-step-bad-ungrounded-001` 报告总分 | 3.464 | **2.85**（门禁值仍 2.75） |
| `anchor_consistency` | — | **1.0（2/2 锚点）** |

测试：`pytest tests/` → **143 passed, 6 skipped**。

---

## 2. 待决策（涉及产品语义或跨仓契约）

| # | 事项 | 选项 / 建议 |
|---|------|-------------|
| D1 | `analyze_multimodal_steps` 是否接线 | 建议**先诊断接线**：让它生成 `rule_findings` 但**不灌进 step score、不改决策**，跑一轮看命中率再定。不要让它去压已冻结的 `judge_scores`（会破坏离线绑定与 κ 基线） |
| D2 | 两套 overall 口径未标注 | 报告总分（`report.overall_score`，含全部已评分步、根因 ×1.5）与门禁值（`min` 媒体步）**是两个数**（实测 2.85 vs 2.75）且进不同产物。要么统一，要么在产物里并列标注 |
| D3 | live 缺维语义 | `extract_dimension_scores` 缺维直接 `raise ValueError`：未评估被表达为**异常**而非状态。需定"异常 vs 显式未评估" |
| D4 | `ProcessRewardReport.overall_score` 改 `Optional[float]` | 完整修法，但有 **13 处消费点**（4 处 `sum()`/`:.2f`/`>=` 会在 `None` 上抛错），且 `overall_score` 会随 `report` 被下游（react-agent）读取。**建议单开 PR 并 bump `EVAL_API_VERSION`**。当前已提供 `scored` / `num_scored` 作权威判据 |

---

## 3. 未验证（本审计未覆盖）

| # | 事项 |
|---|------|
| U1 | live Judge 是否**总**返回四个维度（缺一则 `ValueError`，是另一种失效模式） |
| U2 | `scripts/relabel_expand_human_on_live.py`、`scripts/seed_held_out_expand_human.py` 的具体行为（仅见到文件名） |
| U3 | `examples/fixtures/calibration/multimodal_held_out_expand_human.json` 与夹具的对账（只对账了 `multimodal_dimension_held_out.json` 的 40 项，40/40 相等） |
| U4 | `ArtifactRef.validate()` 的具体约束 |
| U5 | 阈值分裂在**真实评分分布**下的影响面（多少步落在 [3.0, 3.5)）——需真实数据 |

---

## 4. 怎么复现本审计

```bash
# 全量测试
pytest tests/ -q

# 锚点交叉校验（出现在审计报告里）
python examples/run_release_audit.py examples/fixtures/episodes/multimodal_step_ok.json \
  --calibration examples/fixtures/calibration/multimodal_dimension_held_out.json
# → 输出含 "attribution_anchors": {"anchor_consistency": ..., "skipped": [...]}

# live 复核 κ（需 API Key）
python examples/run_release_audit.py ... --live --rebuild-calibration ...
```

CI 侧（Linux，未装 trace-debugger）走的是 **`skipped` 回退路径**：审计不中断，逐条记录
`RuntimeError: trace-debugger is required for rule-failure findings`。

---

## 5. 边界（勿过度解读）

- `anchor_consistency` 是**必要条件通过率**（确定性失败步是否被归因），**不是根因判对率**；42 夹具里 38 条的 `error_sources` 没有锚点可校验，仍需人工标注。
- 本审计是**静态代码审计 + 夹具实测**，不给 live 结论；live 校准（κ）另见 [`METRICS_TRUST.md`](METRICS_TRUST.md) 与 [`HELD_OUT_EXPAND.md`](HELD_OUT_EXPAND.md)。
- 夹具模式读的是**预填 `judge_scores`**（见 `HELD_OUT_EXPAND.md` 协议），其结论只说明**机制**，不等于线上表现。
