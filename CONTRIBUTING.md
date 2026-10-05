# 贡献指南（Contributing）

本仓库维护 Agent 过程级评测（与 [react-agent](https://github.com/weihuaguo270-ops/react-agent) 配套）。欢迎 Issue 与小范围 PR。

```bash
pip install -e ".[test]"
pytest tests/ -q
```

- 勿提交 API Key、真实标注隐私数据
- Commit 建议：`feat:` / `fix:` / `docs:` / `test:`
- 改指标口径或金标准时，同步更新 `docs/METRICS_TRUST.md` 与对应日期快照

## 改 Python 前先扫一遍「内联引号」

```bash
python scripts/check_inline_quotes.py                                          # 默认 scripts/ src/ tests/ examples/
python scripts/check_inline_quotes.py --paths reports/_revoked_20261003/code   # 归档代码需显式传
```

它扫的是**一个具体的、有历史的错误**：在**双引号字符串里再写 ASCII 双引号**去引中文术语
（应当改用 `「」`）。后果是文件直接语法错，或脚本静默失效——两种都难查。

- 依据：`reports/_revoked_20261003/REVOKE_20261003.md` §6 记着这类错误累计犯过 7 次；2026-10-05 又犯了 3 次
- 有可疑行 → 退出码 `1`，可直接接进 CI / pre-commit
- 它**只列候选、并刻意压低假阳性**（裁掉行尾注释、跟踪三引号状态）；**最终以 `compile()` 为准**
- 默认范围**不含 `reports/`**：不想把一个通用于全仓的检查绑死在某个被撤销的目录上
