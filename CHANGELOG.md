# Changelog

## Unreleased

### Changed
- Judge 人机校准 v2：金标准扩至 **28** 条；收紧三份模板边界裁决；offline κ **0.47→0.90**（旧快照保留作基线）
- `run_calibration.py --live` 注入刻度锚点；快照附 `relabel_log` / 残留分歧说明

## 0.1.0 (2026-07-13)

### Added
- Process Reward、动态评分标准、自适应 Eval Loop、HITL
- YAML 评分模板加载、Baseline / Regression gates、校准 demo
- 真实 Judge 集成测试（无 Key 时 skip）

### Changed
- README 定位为实验框架；去掉 Production-grade 表述
- 从 react-agent 拆分为独立仓库（历史）

### Infrastructure
- GitHub Actions CI（lint + pytest）
