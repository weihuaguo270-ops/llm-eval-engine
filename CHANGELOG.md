# Changelog

## Unreleased

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
