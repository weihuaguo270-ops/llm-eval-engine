# 贡献指南（Contributing）

本仓库维护 Agent 过程级评测（与 [react-agent](https://github.com/weihuaguo270-ops/react-agent) 配套）。欢迎 Issue 与小范围 PR。

```bash
pip install -e ".[test]"
pytest tests/ -q
```

- 勿提交 API Key、真实标注隐私数据
- Commit 建议：`feat:` / `fix:` / `docs:` / `test:`
- 改指标口径或金标准时，同步更新 `docs/METRICS_TRUST.md` 与对应日期快照
