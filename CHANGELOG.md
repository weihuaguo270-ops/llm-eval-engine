# Changelog

## Unreleased

### Added (2026-10-04) — 有序量表一致性统计（加权 κ / Krippendorff α / 配对置换检验）

- 新增 `src/eval_engine/judge/agreement.py`：`weighted_kappa`（linear/quadratic）、`krippendorff_alpha`
  （nominal/ordinal/interval，支持多标注者与缺失值）、`paired_permutation_kappa`（版本间配对检验）、
  `ordinal_agreement`（成套输出）。**不替换**既有未加权 `cohens_kappa`（历史口径）。
- `examples/run_calibration.py` 报告新增 `agreement_ordinal` / `inter_rater_ordinal`，快照 md 并列输出。
- 当前 held_out live：人机 κ 未加权 0.8565 → **线性加权 0.9483** → **α(ordinal) 0.9860**；
  标注者间 0.7240 → **0.8974** → **0.9499**。**全部分歧均为相邻档（|差|=1）**，故未加权 κ 低估一致性。
- **据此更正一处误判**：`trajectory_safety` 的「人人 κ=0.5556」是未加权口径的表象，
  同口径线性加权 0.836 / α 0.942 → **不再据此判定 Rubric 不可执行**（改 Rubric 的目标应看 `tool_selection`，其人人 α 最低 0.926）。
- 口径文档：`docs/METRICS_TRUST.md` 新增「有序量表口径」小节（含引用规则：须带统计量与权重、四者不可混比）。
- 测试：新增 `tests/test_agreement_ordinal.py`（11 项，**手算值锁定**）；全量 **175 passed / 5 skipped**。

### Added (2026-10-04) — 结果判断（决策级）+ Rubric 指纹 + 指标自验

- **结果判断（决策级）**：新增 `examples/run_result_evaluation.py`。合格线**逐字来自金标准刻度锚点**并落盘为
  `dataset/data/verdict_bands_line1.json`（**含出处**）；输出逐 template 的判定分布、**缺陷率 + item 级 95% CI**、
  **决策级一致率**、**误杀/漏杀**、判定交叉表。报告按自带 `mode` **自动标注栏位**，非 live 栏打出告警；
  **簇 < 10 不报聚簇 CI**（退化）。当前 held_out live：缺陷率 35.9%/32.1%，**决策级一致率 96.2%**，误杀 0 / **漏杀 2**。（合格线身份：`e939bea70c008429`）
- **Rubric 指纹**：Rubric 文本落审计副本 `dataset/data/rubric_boundary_line1.json`（v2.1，`sha256[:16]=0a780f5ad7916440`）；
  `run_calibration.py` 把 `reproducibility.rubric_boundary_sha256` 写进报告与快照（**+10 行，Rubric 文本逐字节未变**）；
  新增**漂移测试**——改 Rubric 而未同步审计副本/未升版本号 → 测试失败。
- **口径文档**：`EVAL_DESIGN.md` §3.2（合格线表、`blank≠合格`、`unbanded≠合格`、为何必须与 κ 并列）；
  `METRICS_TRUST.md` 新增「结果判断（决策级 · 文本）」一节。
- **测试**：新增 `tests/test_result_verdict.py`（3 项）、`tests/test_rubric_boundary_fingerprint.py`（4 项）；
  全量 **164 passed / 5 skipped**。
- **依据（指标自验，先做后改）**：注入缺陷实验 7 变体 × 11 次 live held_out 运行——刻度反向使 κ 0.8565→**0.4898**
  （证明 Rubric 文本确实驱动 Judge）；删全部边界 κ **−0.26**、删安全类边界 κ **−0.06~−0.09** 均**稳健检出**；
  删锚点/模糊材料为**弱检出（跨阈）**，故小效应需重复 ≥3 次。实验产物在 `reports/_inject_20261003/`（gitignored）。

### Changed (2026-10-01) — 文本 Judge held_out live 引用对齐 v2.1

- held_out live 刷新：κ≈**0.86**（n=53，CI [0.73, 0.97]，DeepSeek）；边界 `rubric_boundary_version=v2.1`
- 快照：`docs/calibration_snapshot_20261001_live_held_out.md`；`reports/calibration_report_20261001_live.json`
- 对外引用同步：`METRICS_TRUST.md`、`README.md`、`EVAL_DESIGN.md`、`SECOND_RATER_PROTOCOL.md`、`CITATION_MULTIMODAL_PROCESS.md`
- 废止对外主钉：held_out live κ≈0.73（2026-08-07，边界 v2）

### Changed (2026-10-01) — 重置 `human_score_r2` 待真人盲标

- 清空校准集全部 `human_score_r2` / `annotator_r2`；`second_rater_status=protocol_ready`
- 重生成 [`docs/second_rater_worksheet.md`](docs/second_rater_worksheet.md)（held_out 53 条）；写满前不报告双人 κ
- `expand_calibration_v5.py` 不再脚本伪造 r2；相关测试与对外引用改为「标注者间未报告」

### Changed (2026-10-01) — 真人 r2 盲标回填

- held_out 53 条 `human_score_r2` 自 worksheet 合并；`second_rater_status=completed_r2_reannotation`
- 初标 κ≈0.55 → 一次修订 κ≈0.64 → 二次修订 κ≈**0.72**（精确一致 81.1%，±1 **100%**）
- 对外文档同步；旧脚本双人 κ≈0.80 继续作废

### Changed (2026-09-30) — API 0.3: `overall_score` is Optional

- `ProcessRewardReport.overall_score` is now `Optional[float]`: `None` means **no step was
  scored** (unscored), never `0.0` (0.0 = worst evidence). `EVAL_API_VERSION` 0.2 → 0.3
- Consumers updated: `benchmark.runner` (unscored cases stay out of `avg_score` and the
  per-category averages), `EvalLoop` (oscillation check skipped while either round is
  unscored), `observability.report`, `__main__`, and the expense / agent-benchmark / e2e
  examples (print `未评估` instead of raising or showing `0.00`)
- `_apply_findings` now enforces `num_scored == 0 ⟺ overall_score is None`: a rule that
  zeroes every step no longer leaves a stale score behind
- **Cross-repo**: react-agent mirrors this constant and must bump in the same release
  (`tests/test_eval_engine_contract.py` asserts both sides are equal)

### Fixed (2026-09-30) — attribution chain audit

- Root-cause threshold follows `min_step_score` (was a hard-coded 3.0), so steps scoring
  in [3.0, 3.5) can no longer be "must fix but never a root cause"
- Unscored steps and judge crashes are no longer counted as failures, root causes, or
  downstream propagation; `unscored` became its own failure type
- Missing process scores are reported as unscored instead of being coerced to 0.0
- Fast mode and scoreless rubrics no longer fabricate zeros or a neutral 3
- Live Judge dimensions stay all-or-nothing: a short payload degrades that step to
  unscored + `judge_error` rather than earning partial credit

### Added (2026-09-30) — attribution chain audit

- Release audit reports `attribution_anchors` (a deterministic failure step should appear
  in `error_sources`), `process_metrics` (gate min vs weighted report score, with explicit
  scopes) and deterministic media `rule_findings` (`source` distinguishes live rules from
  archived `trace_analysis`) — all report-only, none of them change a decision
- `StepScore.applicable` marks steps that are out of process-scoring scope
- `docs/ATTRIBUTION_AUDIT.md`: what was fixed, what is undecided, what is still unverified

### Removed (2026-09-22)

- Deleted generation-side model selection stack: image/video horizontal benches,
  CLIP pairwise leaderboards, blind-review servers, `legacy_generation_bench` docs,
  and **image v2 `offline_real`** evidence claims
- Modules removed: `image_benchmark`, `generation`, `video_benchmark`, `video_generation`,
  `benchmark/leaderboard`; runners `run_real_image/video_benchmark`,
  `run_real_multimodal_leaderboards`, blind-review servers
- Multimodal offline tracks are **understanding-only**

### Added (2026-09-21)

- Soft dimension scores (mean, not min) drive release review below 3.5; held-out κ required before they count
- `examples/run_release_audit.py`: episode → process score → pass/review/hold
- Multimodal-as-trajectory-step vertical slice: `multimodal_step` checks, episode fixtures,
  failure tags (`unnecessary_generation` / `wrong_media_args` / `ungrounded_vision` / `unsafe_media`),
  and process_quality release evidence

### Documentation / Product boundary (2026-09-21 → 2026-09-22)

- Converged product positioning: Agent process eval + release gate is mainline
- Generation-side selection removed (not merely frozen)

## 0.5.0 (2026-08-14)

### Added

- Real image benchmark for SD v1.5 and SD-Turbo with frozen splits, CLIP, safety, latency,
  slice metrics, bootstrap confidence intervals, and blind human review
- Real video benchmark for Wan 2.1 T2V and ModelScope T2V with frame quality, temporal
  consistency, safety, latency, licensing, and artifact checks
- Real-model safety suite and multimodal leaderboard aggregation
- Portfolio readiness audit covering broad Agent application, evaluation, and quality roles
- Expense Agent release pipeline and cross-Agent business evidence gates

### Changed

- Human review supports one full-set rater plus disjoint block-panel raters with shared anchors
- CI verifies multimodal contracts without downloading model weights
- Evidence bundle gates track dataset, version comparison, performance, and human-review evidence

### Evidence

- Image benchmark: 100 prompts, 200 generated PNG files, dev/golden/held-out split
- Video benchmark: 30 prompts, 60 generated MP4 files
- Safety and leaderboard suites marked `offline_real`; human image gate remains pending panel completion

### Verified

- Full local regression: 108 passed, 2 skipped

### Fixed

- Made OpenAI Agents trace evidence non-null by construction so the CI mypy gate can prove span access is safe

### Documentation

- Added real SDK and cross-Agent release commands to the primary reproduction table
- Clarified that the release gate is callable but is not yet a required GitHub Actions job

## 0.4.0 (2026-08-12)

### Added

- `evaluation-episode/v1` with deterministic business-state verification
- Format B, LangGraph, and OpenAI Agents SDK trajectory imports
- Real LangGraph StateGraph and OpenAI Agents Runner integration tests
- Evidence bundle gate for business, process, failure, and performance evidence
- Evidence path normalization and portability contract tests

### Changed

- Agent SDK integrations are optional and isolated from the core evaluator
- Historical report paths use `${WORKSPACE_ROOT}`
- Linux CI verifies Episode imports without the producing Agent SDK

### Verified

- Offline regression: 80 passed
- Real SDK integration: 2 passed

## 0.3.0 (2026-08-11)

### Added

- 数据集 Manifest、Fingerprint、JSONL I/O、split 泄漏审计和标注仲裁
- 多模态 Artifact 契约、元数据完整性指标和外部指标适配接口
- 提示词注入、工具越权、信息外传和良性对照安全回归
- 质量、时延、Token 成本的整体及业务切片漂移检查
- 综合数据、安全、漂移和 held-out Judge 证据的离线发布检查
- 离线评测示例、能力边界说明和带 DRI/日期/依赖的交付计划

### Fixed

- 根因定位的上游低分判断改为使用调用方 threshold，避免 1-5 分制下误标下游节点

### Changed

- README 和评测文档改为项目负责人口径，区分离线原型与未实现的线上闭环
- README、METRICS_TRUST、SECOND_RATER_PROTOCOL 对齐 2026-08-07 live 证据

### Evidence

- held_out live κ≈0.73（n=53，CI [0.58, 0.88]，DeepSeek）
- Live Judge benchmark：32×3（deepseek 46.9% / gpt-4o-mini 40.6% / qwen 15.6%）
- Live Agent benchmark：32/32 pass（DeepSeek，mock Process Reward judge）
- 自动测试：71 passed

## 0.2.0 (2026-07-27)

### Added
- **Benchmark v2**：32 条固定任务（tool/rag/search/safety/faithfulness）+ 三模型 profile 对比
- **react-agent 集成**：`integrations/react_agent.py`、`run_benchmark_agent.py`（mock / live Agent）
- **失败 taxonomy**：`failure_taxonomy.py` + `failure_casebook.md`
- **Eval 设计文档**：`docs/EVAL_DESIGN.md`
- **Live 跑批脚本**：`run_benchmark_live.py`、校准 `--split held_out`
- **CI 回归**：`.github/workflows/benchmark.yml` + shipped `benchmark_baseline.json`
- **E2E demo**：`e2e_trajectory_eval.py`

### Changed
- 校准金标准 **v5**：held_out **n=53**，写入 `human_score_r2`（标注者间 κ≈0.80 offline）
- `BaselineManager` 支持 shipped baseline 回退；回归门禁指标口径统一
- README 改为复现入口与分栏证据（后续 Unreleased 继续收紧表述）

### Evidence (live snapshots, 2026-07-27)
- held_out live κ≈**0.67**（n=53，CI [0.52, 0.82]）
- Live Agent benchmark：**32/32** pass（DeepSeek react_loop）
- Benchmark live Judge：3-case smoke 66.7% pass

## 0.1.0 (2026-07-13)

### Added
- Process Reward、动态评分标准、自适应 Eval Loop、HITL
- YAML 评分模板加载、Baseline / Regression gates、校准 demo
- 真实 Judge 集成测试（无 Key 时 skip）
- **P2 API 版本钉**：`EVAL_API_VERSION = "0.1"`（与 react-agent 对齐）

### Changed
- 从 react-agent 拆分为独立实验仓库
- Judge 人机校准 v4、CI hardening（Windows / cov / mypy / pip-audit）

### Infrastructure
- GitHub Actions CI（lint + pytest）
