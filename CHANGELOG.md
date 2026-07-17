# Changelog

## Unreleased

### Added
- **P2 API 版本钉**：`EVAL_API_VERSION = "0.1"`（与 react-agent `EVAL_ENGINE_API_CONTRACT` 对齐）

### Changed
- Judge 人机校准：**v4** held_out 已标 **20** + pending 3；第二标注者协议/worksheet；门禁文案标明 gate_split
- CI：Windows × 3.10/3.11、pytest-cov、mypy、pip-audit
- 公开口径统一为 held_out live κ≈**0.69**（n=20，v4 live 重跑）；废弃 n=15/κ≈0.47 与扩容前 n=11/κ≈0.59
- Judge 校准 v2→v3：金标准 28；offline 全量 κ **0.47→≈0.90**；引入 dev/held_out
- `run_calibration.py --live`：DeepSeek v4；held_out κ≈**0.69**（CI [0.46, 0.92]，门禁已过）

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
