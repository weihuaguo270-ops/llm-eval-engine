# Changelog

## Unreleased

### Changed
- Judge 人机校准 v2：金标准扩至 **28** 条；收紧三份模板边界裁决；offline κ **0.47→0.90**（旧快照保留作基线）
- `run_calibration.py --live`：自动从姊妹仓 `.env` 映射 DeepSeek Key；live κ≈**0.68**（`docs/calibration_snapshot_20260716_live.md`）
- **v3 指标可信度**：`dev`/`held_out` 分栏、bootstrap 95% CI、`docs/METRICS_TRUST.md`；第二标注者标记 pending

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
