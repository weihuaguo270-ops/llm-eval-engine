# 归因审计（Attribution Audit）

**审计对象：** `ProcessRewardScorer` → `report.error_sources`（根因步）→ release audit 这条链路。
**方法：** 静态代码审计 + 42 个 episode 夹具实测（默认夹具模式）；**未跑 live**。
**日期：** 2026-09-30 · 对应 PR（均已 squash 合并）：llm-eval-engine #8 `75b951a`（审计主体）、#9 `c29cbc2`（§1.1 的 P2 三项）、#11 `c86b6d6`（§1 第 13 项，原 D4；原 PR #10 因 #9 合并时删除 head 分支被 GitHub 自动关闭，内容由 #11 承接）、trace-debugger #8、react-agent #105 `ddb4a2d`（跨仓 `EVAL_API_VERSION` 0.3）。

**2026-10-01 更新：** §3 重写为「已核实关闭 / 已处置 / 带验收条件的阻塞项」三类，并补上离线实测数字（U1/U5/U8）；U6 重新生成 casebook 并加 CI 防漂移。

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

| 13 | **`overall_score` 二态**：一个步都没评上时也报 `0.0`——与"评了 0 分"（最差证据）无法区分，会污染均值与阈值比较 | `avg_score`、Eval Loop 振荡判定、CLI/报告都把这个 `0.0` 当真实分数读 | **已修（原 D4）**：`overall_score: Optional[float]`（`None` = 未评估），逐处消费点显式判 `None`；`_apply_findings` 维持 `num_scored == 0 ⟺ overall_score is None`；`EVAL_API_VERSION` 0.2 → 0.3（**需 react-agent 配套 PR**） |

### 修复后的实测（42 个 episode 夹具，夹具模式）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 报出 `error_sources` 的 episode | **40 / 42** | **2 / 42** |
| `needs_revision` 的 episode | 40 | **40（不变）** |
| 门禁/决策分布 | 40 review / 2 pass | **40 review / 2 pass（不变）** |
| `num_scored == 0` 的 episode | 0 | **38 / 42**（诚实暴露"没评过"） |
| `mm-step-bad-ungrounded-001` 报告总分 | 3.464 | **2.85**（门禁值仍 2.75） |
| `anchor_consistency` | — | **1.0（2/2 锚点）** |

测试：`pytest tests/` → **150 passed, 6 skipped**。

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

当前无待决策项。原 D4 已落地（见 §1 第 13 项），跨仓配套也已完成：llm-eval-engine #11（0.3）与 react-agent #105 均已合并，两边 `EVAL_API_VERSION` 都是 `0.3`（react-agent 从本仓 master 装机，并在 `tests/test_eval_engine_contract.py` 断言两边相等）。

---

## 3. 未验证项的处理（2026-10-01 更新）

原 U1–U8 分三类：**已核实关闭**（U2/U3/U4）、**已处置**（U6 修复、U7 澄清）、**带验收条件的阻塞项**（U1/U5/U8）。

### 3.1 已核实关闭

| # | 原问题 | 结论与证据 |
|---|--------|-----------|
| U2 | 两个 expand 脚本的行为 | `scripts/seed_held_out_expand_human.py:150-192`：遍历 36 个 expand 夹具，为每个媒体/终态步 × 4 维写死人工分，**缺任何一格即 `SystemExit`**（:162），输出 `judge_score: None` 待回填，meta 记 `labeler: r1-maintainer` / `second_rater_status: pending`（:182-184）。`scripts/relabel_expand_human_on_live.py:22-46`：读 `reports/multimodal_held_out_expand_live.json`，按 `(episode_id, step_index, dimension)` 用人工分覆盖 live 行，打印覆盖前后 κ/MAE，回写并加 note。**含义**：该链的 κ 是「判分器 vs 单一维护者」（无第二评分者），且人工分与判分器同源于协议文档，存在循环性风险——与 U8 同根因 |
| U3 | expand 人工标注与夹具对账 | **已由测试覆盖**：`tests/test_held_out_expand_seed.py:29-55` 逐格 `indexed[(episode, step, dim)]`（缺失即 KeyError）、断言 `human_score` 非空与 `judge_score is None`、`rebuild_held_out_calibration` 后全非空且条数 == `sample_size_human_cells`。原判断「只对账了 40 项那份」已过时 |
| U4 | `ArtifactRef.validate()` 约束 | `src/eval_engine/multimodal/evaluator.py:52-69`：`id` 非空、`media_type ∈ {image,video,audio,document,other}`、`uri` 非空、**`sha256` 可空**（非空须 64 位十六进制）、`width/height > 0`、`duration_ms/frame_count ≥ 0`；`from_dict`（:35-36）另拒内嵌 `data`/`base64`。「缺 sha」类规则的存在空间正来自 `sha256` 可空 |
| U6 | casebook 与重生成不一致 | **提交的是旧脚本产物（陈旧），生成器本身可复现**：连跑两次文件哈希相同。本 PR 重新生成并提交，并在 `benchmark.yml` 增加 `git diff --exit-code -- docs/failure_casebook.md`，防止再次漂移 |
| U7 | 日期戳产物不入库 | **属约定、非缺陷**：`docs/benchmark_comparison_*.md` 是被 README 引用的**证据报告**（`README.md:86,96,98`），机器产物是 `reports/*.json`（已 gitignore）。CI 每次跑批都会生成这些文件但不提交，属预期行为，无需改代码 |

### 3.2 带验收条件的阻塞项

| # | 缺口 | 现有证据 | 关闭条件 |
|---|------|----------|----------|
| U1 | live Judge 的真实维度分布 | **归档 live 实测已可用**（`reports/multimodal_held_out_expand_live.json`，36 轨迹）：**312 格 / 78 步，`judge_score` 空值 0，步-维直方图 = {4: 78}**（四维各 78 次，即该批四维齐全）；`reports/release_audit_held_out_expand_live.json` 的 `calibration` 块 **κ=0.617，n=312**，与 `HELD_OUT_EXPAND.md:39` 的 ≈0.62（CI [0.54,0.69]）一致 | 长期监测（不阻塞）：后续 live 运行缺维步占比保持 0；一旦缺维，按 §1 第 4 项/原 D3 降级为 `judge_error` + 未评估，可在 `failure_taxonomy` 计数 |
| U5 | 阈值带 [3.0,3.5) 的**真实**分布 | 离线代理（本轮实测）：随包 benchmark 32 用例 × 3 模型共 **324 步**，带内 **15 步（占已评分步 4.63%），且 15/15 `needs_revision=True`**——修复前这 15 步「必须修却永远不可能被判为根因」；42 个夹具只有 4 条有分数（10 步，带内 1 步），**38/42 未评估** | 在真实评分数据上给出带内步占比与受影响用例数；敏感性：即使真实分布比 benchmark 偏 2–3 倍，受影响面仍在同一量级 |
| U8 | 两条媒体规则链的真阳性率 | **一致性基线（42 夹具全量，本轮实测）**：两链同时为空 **31**；仅规则命中 **9**；仅归档命中 **1**；都有但不等 **1**；**同为非空且完全一致 0**。分歧集中在 `unsafe_media`（4 条仅规则）、`wrong_media_args` / `unnecessary_generation`（仅规则）、`ungrounded_vision`（仅归档） | 需要**独立**失败类型标注（现有标注是维度分、且仅 1 名标注者）：先定标注协议（标什么、条数、κ 阈值），取得 ≥30 条金标准后计算 P/R，据此把 D5 从 (c) 收敛到 (a)/(b) |

### 3.3 一个易混点（本轮踩到并更正）

本仓同时存在两套 κ，**不可互换**：

| 校准集 | 来源 | n | κ |
|--------|------|---|----|
| 文本 / Agent 过程 | `src/eval_engine/dataset/data/calibration_human_judge.json`（`reports/calibration_report_20261001_live.json` 的 `source_path`） | 53 | **0.8565**（inter-rater 0.7979，最差维度 `overall`） |
| 多模态四维 expand | `examples/fixtures/calibration/multimodal_held_out_expand_human.json` | 312 | **0.617**（与 `HELD_OUT_EXPAND.md:39` 一致） |

引用 κ 时必须写明是哪一套；把 0.8565 当成多模态结论、或把 53 格当成 expand 的覆盖面，都是错的。

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
