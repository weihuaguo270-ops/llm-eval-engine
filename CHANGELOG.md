# Changelog

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
- README 更新为 Mid 档评测交付物口径

### Evidence (live snapshots, 2026-07-27)
- held_out live κ≈**0.67**（n=53，CI [0.52, 0.82]）
- Live Agent benchmark：**32/32** pass（DeepSeek react_loop）
- Benchmark live Judge：3-case smoke 66.7% pass

## Unreleased

## 0.1.0 (2026-07-13)

### Added
- Process Reward、动态评分标准、自适应 Eval Loop、HITL
- YAML 评分模板加载、Baseline / Regression gates、校准 demo
- 真实 Judge 集成测试（无 Key 时 skip）
- **P2 API 版本钉**：`EVAL_API_VERSION = "0.1"`（与 react-agent 对齐）

### Changed
- README 定位为实验框架；从 react-agent 拆分为独立仓库
- Judge 人机校准 v4、CI hardening（Windows / cov / mypy / pip-audit）

### Infrastructure
- GitHub Actions CI（lint + pytest）
