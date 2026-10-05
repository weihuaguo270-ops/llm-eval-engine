"""`scripts/check_inline_quotes.py` 的回归测试——**锁住它的假阳性率**。

为什么这个测试本身值得写：这个扫描器第一版**报 20 处、其中 19 处是假阳性**
（没裁行尾注释、没识别三引号开头的行）。一个信噪比那样的检查等于逼人忽略它。
所以这里把"该报的"与"**不该报的**"都钉住——**后者才是它的价值所在**。

夹具的一个陷阱（也是为什么夹具都用 `%` 占位符拼）
--------------------------------------------------
本文件会被扫描器自己扫到（默认范围含 `tests/`）。如果夹具里直接写汉字引号，
**扫描器就会把夹具当成真问题**，全仓零命中那条断言会失败。
故所有夹具用 `_zh()` 把 `%` 换成汉字，让**本文件的源码里不出现那个模式**。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_inline_quotes.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_inline_quotes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CIQ = _load()


def _zh(template: str) -> str:
    """把占位符 `%` 换成汉字，**使本文件源码自身不含那个模式**。"""
    return template.replace("%", "\u4e2d\u6587")


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ── 该报的 ──────────────────────────────────────────────────────────────────


def test_flags_quotes_inside_a_code_string(tmp_path):
    """代码行里出现「汉字+ASCII双引号+汉字」→ 必须报。"""
    path = _write(tmp_path, "bad.py", _zh('note = "%"%"') + "\n")

    hits = CIQ.scan_files([path])

    assert len(hits) == 1, f"应恰好报 1 处，实报 {hits}"
    assert hits[0][1] == 1


def test_flags_bad_line_after_a_docstring_closes(tmp_path):
    """文档串闭合**之后**的坏行仍要报 —— 这条锁住 `in_doc` 状态机两个方向都能翻。"""
    path = _write(tmp_path, "mixed.py", _zh('"""文档串，含"%"这种。"""\nnote = "%"%"') + "\n")

    hits = CIQ.scan_files([path])

    assert [line for _shown, line, _code in hits] == [2], "只应报第 2 行"


# ── **不该报的**（这几条才是重点） ─────────────────────────────────────────


def test_ignores_quotes_in_a_trailing_comment(tmp_path):
    """行尾注释里的引号是合法的 —— 不裁注释就会产生大量假阳性。"""
    path = _write(tmp_path, "comment.py", _zh('x = 1   # 两种"%"不同') + "\n")

    assert CIQ.scan_files([path]) == []


def test_ignores_full_line_comment(tmp_path):
    path = _write(tmp_path, "whole.py", _zh('# 这里说"%"都可以') + "\n")

    assert CIQ.scan_files([path]) == []


def test_ignores_quotes_inside_a_docstring(tmp_path):
    """多行文档串**内部**的引号合法 —— 不识别三引号状态就会误报。"""
    text = _zh('"""开头。\n说明：把"%"记下来。\n"""\nx = 1\n')
    path = _write(tmp_path, "doc.py", text)

    assert CIQ.scan_files([path]) == []


def test_ignores_one_line_docstring_and_comments(tmp_path):
    """一行内自闭合的文档串不该把状态翻错（`count('\"\"\"') % 2` 的作用）。"""
    text = _zh('"""一行文档串，含"%"这种。"""\n# 注释："%"\ny = 2\n')
    path = _write(tmp_path, "oneline.py", text)

    assert CIQ.scan_files([path]) == []


# ── code_part 的边界 ────────────────────────────────────────────────────────


def test_code_part_truncates_trailing_comment_and_skips_docstring_openers():
    assert CIQ.code_part('    x = 1  # 注释') == "x = 1"
    assert CIQ.code_part("    # 整行注释") == ""
    assert CIQ.code_part('    """文档串开头') == ""
    assert CIQ.code_part("'''也是文档串'''") == ""
    assert CIQ.code_part("    ") == ""


# ── 退出码与范围 ────────────────────────────────────────────────────────────


def test_exit_code_is_one_on_hits_and_zero_when_clean(tmp_path, capsys):
    clean = _write(tmp_path, "clean.py", "x = 1\n")
    bad = _write(tmp_path, "bad.py", _zh('note = "%"%"') + "\n")

    assert CIQ.main(["--paths", str(clean)]) == 0
    assert CIQ.main(["--paths", str(bad)]) == 1
    capsys.readouterr()


def test_iter_python_files_skips_vendor_dirs(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.py").write_text("z = 3\n", encoding="utf-8")

    names = {path.name for path in CIQ.iter_python_files([tmp_path])}

    assert names == {"a.py"}, f"`.venv` / `__pycache__` 不得进入：{names}"


def test_default_roots_all_exist_in_this_repo():
    """默认范围里的目录**必须真的存在**——否则默认扫描会静默变成空扫。"""
    missing = [name for name in CIQ.DEFAULT_ROOTS if not (REPO / name).is_dir()]
    assert missing == [], f"默认范围里有不存在的目录：{missing}"


def test_repository_is_clean(capsys):
    """全仓默认范围必须**零命中**——同时是"本仓库当前没有这类错误"的回归守卫。

    归档代码**不在**默认范围内（`reports/` 是归档数据）；要扫它得显式 `--paths`。
    """
    exit_code = CIQ.main([])
    capsys.readouterr()

    assert exit_code == 0, "默认范围内出现可疑代码行——要么是真错，要么是假阳性，两种都要修"
