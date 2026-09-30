# 归因审计（Attribution Audit）

**审计对象：** `ProcessRewardScorer` → `report.error_sources`（根因步）→ release audit 这条链路。
**方法：** 静态代码审计 + 42 个 episode 夹具实测（默认夹具模式）；**未跑 live**。
**日期：** 2026-09-30 · 对应 PR：llm-eval-engine #8（审计主体，已 squash 合并 `75b951a`）、llm-eval-engine #9（§1.1 的 P2 三项）、trace-debugger #8（已 squash 合并）。

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
| 12 | **（跨仓）媒体规则孤岛**：trace-debugger 的 `analyze_multimodal_steps`（精确规则：空 prompt / 缺 path / sha 不匹配 / 终态未引用 / NSFW）**只被测试调用**；审计走 `adapt_media_rule_findings(metadata.trace_analysis)`，而该上游当前**不产出**那 4 个媒体类型 | 报告里"媒体规则证据"几乎恒空——**覆盖假象** | **已修（原 D1）**：审计报告接线确定性规则，与归档 analysis 按 `(step_index, failure_type)` 去重合并，**只报告、不参与决策** |

### 修复后的实测（42 个 episode 夹具，夹具模式）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 报出 `error_sources` 的 episode | **40 / 42** | **2 / 42** |
| `needs_revision` 的 episode | 40 | **40（不变）** |
| 门禁/决策分布 | 40 review / 2 pass | **40 review / 2 pass（不变）** |
| `num_scored == 0` 的 episode | 0 | **38 / 42**（诚实暴露"没评过"） |
| `mm-step-bad-ungrounded-001` 报告总分 | 3.464 | **2.85**（门禁值仍 2.75） |
| `anchor_consistency` | — | **1.0（2/2 锚点）** |

测试：`pytest tests/` → **146 passed, 6 skipped**。

### 1.1 P2 三项（原 D1–D3，已落地）

| # | 事项 | 做法 | 关键证据 |
|---|------|------|----------|
| 原 D1 | `analyze_multimodal_steps` 接线 | `release_audit._media_rule_findings()` 合并「确定性规则」与「归档 `trace_analysis` 适配项」，按 `(step_index, failure_type)` 去重；`source` 字段区分 `multimodal_step` / `trace_debugger`；**只写报告、不参与决策、不碰 step score** | 见下「规则与归档不一致」 |
| 原 D2 | 两套 overall 口径 | 报告新增 `process_metrics`（顶层 + 每 episode）：`gate_media_min` / `gate_scope` / `report_weighted` / `report_scope` / `gate_applied` / `num_scored` / `num_steps`；`process_quality_from_report` 输出加 `overall_score_scope` | image-bad：`gate_media_min=2.75` vs `report_weighted=2.85`；未标定时 `gate_applied=false` 且 `gate_media_min=null`（值算出但不作门禁） |
| 原 D3 | live 缺维语义 | **不改**：`extract_dimension_scores` 仍 `raise ValueError("live Judge missing dimensions: ...")`，由 scorer 逐步兜住——该步 `applicable=True`、`step_score=0.0`、`needs_revision=True`，taxonomy 记 `judge_error`，`num_scored=0` → `overall_score=None` | 钉在 `tests/test_release_audit_live_judge.py::test_incomplete_live_dimensions_degrade_to_unscored_not_a_crash` |

**原 D3 被否决的替代方案：** 「缺维度就给已有维度的部分学分」——那会把**判分器输入错误**伪装成**低分证据**，再经根因 ×1.5 加权污染 `error_sources` 归因（正是本审计要消灭的假根因）。因此保留 all-or-nothing，把"未评估"表达为**状态**而非分数。

**规则与归档不一致（原 D1 实测，尚需裁决）：**

| 夹具 | 确定性规则 | 归档 `trace_analysis` |
|---|---|---|
| `multimodal_step_bad.json` | `(1, unnecessary_generation)`、`(1, wrong_media_args)` | `(1, unnecessary_generation)` |
| `multimodal_step_video_bad.json` | 无 | `(2, ungrounded_vision)` |
| `multimodal_step_ok.json` | 无 | 无 |

去重后：image 2 条（`source` 全为 `multimodal_step`）、video 1 条（`trace_debugger`）。**两者互不覆盖**：规则漏了 video 的 `ungrounded_vision`，归档漏了 image 的 `wrong_media_args`。接线后报告同时可见两种证据，但**哪个才是对的尚未裁决**（见 §2 D5）。

---

## 2. 决策与待决策（涉及产品语义或跨仓契约）

### 2.1 已决策

| # | 事项 | 决策 | 理由 / 收敛条件 |
|---|------|------|-----------------|
| D5 | 规则 vs 归档谁是权威 | **(c) 并列展示、标注来源**（`rule_findings[].source`），两者都不进决策 | 没有任何金标准标签能算出 P/R（见 U8），此时选 (a) 或 (b) 只是**用偏好替代证据**；而"看不见"是当前真正的缺陷。**收敛条件**：一旦有了人工标注的媒体失败金标准，再按 P/R 收敛到 (a) 或 (b)，并删除败者 |

### 2.2 待决策

| # | 事项 | 选项 / 建议 |
|---|------|-------------|
| D4 | `ProcessRewardReport.overall_score` 改 `Optional[float]` | 完整修法，但有 **13 处消费点**（4 处 `sum()`/`:.2f`/`>=` 会在 `None` 上抛错），且 `overall_score` 会随 `report` 被下游（react-agent）读取。**已单开 stacked PR（见 PR #10）并 bump `EVAL_API_VERSION`**。当前已提供 `scored` / `num_scored` 作权威判据 |

---

## 3. 未验证（本审计未覆盖）

| # | 事项 |
|---|------|
| U1 | live Judge 是否**总**返回四个维度：缺维时的**行为**已在原 D3 钉住；**真实返回维度分布仍未测**（本审计未跑 live，无 API Key） |
| U2 | `scripts/relabel_expand_human_on_live.py`、`scripts/seed_held_out_expand_human.py` 的具体行为（仅见到文件名） |
| U3 | `examples/fixtures/calibration/multimodal_held_out_expand_human.json` 与夹具的对账（只对账了 `multimodal_dimension_held_out.json` 的 40 项，40/40 相等） |
| U4 | `ArtifactRef.validate()` 的具体约束 |
| U5 | 阈值分裂在**真实评分分布**下的影响面（多少步落在 [3.0, 3.5)）——需真实数据 |
| U6 | `docs/failure_casebook.md` 与重新生成结果**不一致**：本地重跑 `scripts/generate_failure_casebook.py` 得到 `106 insertions(+), 109 deletions(-)`（条目顺序与页头都不同）→ 提交的副本是旧的或手改过，生成器**不可字节复现**。本次未修（与归因链路无关） |
| U7 | `examples/run_benchmark.py` 每次产出**日期戳新文件**（`docs/benchmark_comparison_<date>.md`），不入版本库；基准回归门禁本地实测 **PASS**（3.647 vs 3.613，+0.034），即本次改动未移动基准总均值 |
| U8 | `release_audit` 与 `trace_rules` 两条媒体规则链的**真阳性率**：本次只做到"并列展示"，没有金标准标签可算 P/R |

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
- `rule_findings` / `process_metrics` / `attribution_anchors` 都是**报告字段**：改动它们**不改变任何 decision**。P2 三项没有动门禁逻辑（门禁改动只在 §1 的 1–9 项）。
- 原 D1 的接线只让证据**可见**，不代表证据**正确**：规则与归档在 3 个夹具上互不覆盖（§1.1），裁决见 §2 D5。
