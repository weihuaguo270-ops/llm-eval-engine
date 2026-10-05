"""文档里报告的合格线派生数字，**必须自带合格线身份**（计划 P4）。

为什么需要它：P1–P3 只让**新**产物带身份。文档里引用的历史数字（缺陷率／决策级一致率）
若不带身份，读者就分不清「已核对过判据」与「从没核对过」——那正是本仓
「**未标不得当作通过**」这条纪律要防的事。

## 匹配范围（**故意很窄**）

一行同时满足才检查：含 `缺陷率` 或 `决策级`，**且报了一个率**（``\\d+(\\.\\d+)?%``，
但**排除置信水平** ``95% CI`` 里的百分数——那是区间，不是率）。

窄是刻意的：`scripts/check_inline_quotes.py` 第一版匹配过宽，20 个命中里 19 个是误报。
**已知未覆盖**：只报计数的行（「误杀/漏杀 0 / 2」「判定分布 pass 29/29」）不在**必填**范围内
——它们同样依赖合格线，但与普通叙述区分开需要更精确的解析，本版不做。
不过**凡已出现的标记**（含手工加在这些行上的）都会被校验，所以过期标记照样会被抓。

## 检查两件事

1. 命中的行**必须**带标记：``合格线身份：<hex>`` 或 ``合格线身份：未登记``；
2. **每一个**标记里的 `<hex>` 必须等于**当前** `verdict_bands_line1.json` 算出的身份
   —— 于是**合格线一改，这里就失败**，逼人重新标注或重算（这正是 P4 要的"会失败"）。

用法::

    python scripts/check_verdict_citations.py     # 0 = 通过；1 = 有违规；2 = 合格线不可识别
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

from eval_engine.core.verdict import bands_identity  # noqa: E402

#: 判定标准的来源：文档里的标记必须与**这个文件当前内容**算出的身份一致
BANDS_FILE = REPO / "src" / "eval_engine" / "dataset" / "data" / "verdict_bands_line1.json"

#: 检查范围**只含被跟踪的文档**——`reports/` 在 `.gitignore` 内，归档报告不在此列
TARGETS = ("docs", "README.md", "CHANGELOG.md", "AGENTS.md", "CONTRIBUTING.md")

RATE_KEYWORDS = ("缺陷率", "决策级")
RATE_RE = re.compile(r"\d+(?:\.\d+)?%")
#: **误报防线**：`95% CI` 里的百分数是**置信水平**，不是报出来的率。
#: 第一版没排除它，于是「缺陷率 + item 级 95% CI」这种只**列举输出项**的行也被要求带标记
#: —— 是逐条审计命中行时才发现的。
CI_LEVEL_RE = re.compile(r"\d+%\s*CI")
HEX_MARKER_RE = re.compile(r"合格线身份：\s*`?([0-9a-f]{8,64})`?")
UNREGISTERED_RE = re.compile(r"合格线身份：\s*未登记")


def reports_a_rate(line: str) -> bool:
    """该行是否**报了一个率**（而不是只在列举输出项、或写置信水平）。

    已知未覆盖：只写置信区间、不写点估计的行（如「95% CI [0.208, 0.453]」）落在判定之外——
    把它们算进来就会重新引入上面那类误报。
    """
    return RATE_RE.search(CI_LEVEL_RE.sub("", line)) is not None


def iter_targets(repo: Path = REPO):
    """产出待检查的文档路径（目录递归取 `*.md`）。"""
    for name in TARGETS:
        path = repo / name
        if path.is_dir():
            yield from sorted(path.rglob("*.md"))
        elif path.is_file():
            yield path


def find_violations(paths, expected_sha256: str):
    """返回 ``[(path, lineno, kind, detail)]``；``kind`` 为 ``missing`` 或 ``stale``。"""
    violations = []
    for path in paths:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            markers = HEX_MARKER_RE.findall(line)
            flagged = any(key in line for key in RATE_KEYWORDS) and reports_a_rate(line)
            if flagged and not markers and not UNREGISTERED_RE.search(line):
                violations.append((path, lineno, "missing", line.strip()[:90]))
            for value in markers:
                if not expected_sha256.startswith(value):
                    violations.append((path, lineno, "stale", value))
    return violations


def main() -> int:
    identity = bands_identity(BANDS_FILE)
    if identity["recognized"] is not True or not identity["sha256"]:
        print(f"❌ 合格线不可识别（{identity['reason']}）→ 无法校验文档标记")
        return 2
    expected = identity["sha256"]
    paths = list(iter_targets())
    violations = find_violations(paths, expected)

    print(
        f"扫描 {len(paths)} 个文档｜合格线身份 {expected[:16]}"
        f"（{len(identity['dimensions'])} 维）｜违规 {len(violations)} 处"
    )
    for path, lineno, kind, detail in violations:
        label = "缺标记" if kind == "missing" else "标记过期"
        print(f"  ✗ {path.relative_to(REPO).as_posix()}:{lineno} [{label}] {detail}")
    if violations:
        print()
        print("修法：报告合格线派生数字的行上写 `合格线身份：<sha256 前缀>`；")
        print("      判据无法追溯的（如归档那条线）写 `合格线身份：未登记`。")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
