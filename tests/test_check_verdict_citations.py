"""文档里的合格线派生数字必须自带身份（计划 P4）——检查器本身的测试。

**这条测试的重点是"检查器不空转、也不误报"**：
`scripts/check_inline_quotes.py` 第一版因为匹配过宽，20 个命中里 19 个是误报，
所以这里对两侧都设了防线。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_verdict_citations", REPO / "scripts" / "check_verdict_citations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_docs_pass_and_the_check_is_not_vacuous():
    """真仓必须 0 违规；**且命中行不能是 0**——否则这条检查在空转。"""
    module = _checker()
    expected = module.bands_identity(module.BANDS_FILE)["sha256"]
    paths = list(module.iter_targets())

    assert module.find_violations(paths, expected) == [], "真仓文档有违规"

    checked = [
        (path, line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if any(key in line for key in module.RATE_KEYWORDS) and module.reports_a_rate(line)
    ]
    assert len(checked) >= 5, f"命中行只有 {len(checked)} 行 → 检查可能已空转"


def test_missing_marker_is_a_violation(tmp_path):
    doc = tmp_path / "a.md"
    doc.write_text("| 缺陷率 | 35.9% |\n", encoding="utf-8")
    violations = _checker().find_violations([doc], "e" * 64)
    assert violations and violations[0][2] == "missing"


def test_stale_marker_is_a_violation(tmp_path):
    """合格线一改，旧标记必须被判过期——这是 P4「会失败」的那一半。"""
    doc = tmp_path / "a.md"
    doc.write_text("| 缺陷率 | 35.9%（合格线身份：`0000000000000000`） |\n", encoding="utf-8")
    violations = _checker().find_violations([doc], "e" * 64)
    assert violations and violations[0][2] == "stale"


def test_unregistered_marker_is_accepted(tmp_path):
    """判据无法追溯的（如归档那条线）写「未登记」即可——**不得补造**身份。"""
    doc = tmp_path / "a.md"
    doc.write_text("| 缺陷率 | 35.9%（合格线身份：未登记） |\n", encoding="utf-8")
    assert _checker().find_violations([doc], "e" * 64) == []


def test_prose_without_a_rate_is_not_flagged(tmp_path):
    """**误报防线**：提到"缺陷率"但没报率的叙述，不该被要求带标记。"""
    doc = tmp_path / "a.md"
    doc.write_text(
        "缺失合格线时，缺陷率会显示 0（最好看的数）。\n"
        "| 判定分布 | pass 29/29 |\n",
        encoding="utf-8",
    )
    assert _checker().find_violations([doc], "e" * 64) == []


def test_published_identity_is_the_tracked_bands_file():
    """文档里写的身份必须来自那份**被跟踪**的合格线——且它自 `a2b79a8` 起未变。"""
    module = _checker()
    identity = module.bands_identity(module.BANDS_FILE)
    assert identity["recognized"] is True
    assert identity["sha256"][:16] == "e939bea70c008429"


def test_confidence_level_percent_is_not_a_rate(tmp_path):
    """**误报防线（实测踩到过）**：`95% CI` 里的百分数是置信水平，不是报出来的率。

    第一版没排除它，于是「输出：…缺陷率 + item 级 95% CI…」这种只**列举输出项**的行
    也被要求带标记——是逐条审计命中行时才发现的。
    """
    doc = tmp_path / "a.md"
    doc.write_text(
        "**输出**：逐 template 的判定分布、**缺陷率 + item 级 95% CI**、**决策级一致率**、\n",
        encoding="utf-8",
    )
    assert _checker().find_violations([doc], "e" * 64) == []
