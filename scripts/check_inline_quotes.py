#!/usr/bin/env python
"""check_inline_quotes — 扫出「在代码行里把中文引号写成 ASCII 双引号」这一类语法错误。

**为什么需要它**（这不是通用 lint，是本仓库的历史痛点）
--------------------------------------------------------
`reports/_revoked_20261003/REVOKE_20261003.md` §6 记着：这类错误**作者累计犯过 7 次**；
2026-10-05 的会话里又犯了 3 次（第 8 / 9 / 10 次），每次都让脚本静默失效或直接语法错。
靠 `compile()` 抓，**一次只能抓到某个文件的第一处**，于是退化成
「修一处 → 跑一次 → 又炸一处」——那一次连着四轮。

**判据**
--------
非注释、且不在三引号串内，出现「汉字 + ASCII 双引号 + 汉字」。

⚠️ **它区分不了合法与非法**，只把候选缩到几行；**最终以 `compile()` 为准**。
⚠️ **假阳性必须压到零**，否则没人会看它——两条必须做的裁剪
（第一版漏了它们，20 个命中里 19 个是噪声）：
   ① 截掉**行尾注释**；
   ② **以三引号开头的行**整行跳过（那行的引号在文档串内）。

**用法**
--------
::

    python scripts/check_inline_quotes.py                     # 默认扫 scripts/ src/ tests/ examples/
    python scripts/check_inline_quotes.py --paths src tests
    python scripts/check_inline_quotes.py --paths reports/_revoked_20261003/code

默认**不含 `reports/`**：免得把一个通用于全仓的检查绑死在某个被撤销的目录上。
归档代码要显式用 `--paths` 传（本仓库确实会编辑那批文件）。

**退出码**：有可疑行 → `1`；干净 → `0`（可直接接进 CI / pre-commit）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

#: 汉字 + ASCII 双引号 + 汉字
SUSPECT = re.compile(r'[\u4e00-\u9fff]"[\u4e00-\u9fff]')

#: 默认扫描的代码目录（相对仓库根）
DEFAULT_ROOTS = ("scripts", "src", "tests", "examples")

#: 永不进入的目录名（出现在路径的任一段即跳过）
SKIP_DIRS = frozenset(
    {".git", ".venv", ".venv-root", "__pycache__", ".pytest_cache", "node_modules"}
)


def iter_python_files(paths: Sequence[Path]) -> list[Path]:
    """把目录/文件参数展开成 `.py` 文件清单（目录递归，跳过 `SKIP_DIRS`）。"""
    out: list[Path] = []
    for path in paths:
        if path.is_file():
            out.append(path)
            continue
        if not path.is_dir():
            continue
        for candidate in sorted(path.rglob("*.py")):
            if SKIP_DIRS & set(candidate.parts):
                continue
            out.append(candidate)
    return out


def code_part(line: str) -> str:
    """取一行的**代码部分**：整行注释或三引号开头 → 空串；否则截掉行尾注释。

    粗口径：不考虑「字符串里含 `#`」这种少见情形——本检查只用于缩小候选范围。
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return ""
    hash_pos = stripped.find("#")
    if hash_pos != -1:
        stripped = stripped[:hash_pos].rstrip()  # 截掉注释后还要去尾空格（返回值会打印给用户看）
    if stripped.lstrip().startswith('"""') or stripped.lstrip().startswith("'''"):
        return ""  # 本行在代码位置开启了文档串 → 其后内容属串内
    return stripped


def scan_files(files: Sequence[Path]) -> list[tuple[str, int, str]]:
    """逐文件扫描，返回 ``[(显示路径, 行号, 代码行), …]``。"""
    hits: list[tuple[str, int, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            shown = str(path.relative_to(REPO))
        except ValueError:
            shown = str(path)
        in_doc = False
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not in_doc:
                code = code_part(line)
                if code and SUSPECT.search(code):
                    hits.append((shown, lineno, code[:120]))
            if stripped.count('"""') % 2 == 1:
                in_doc = not in_doc
    return hits


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="扫出「代码行里把中文引号写成 ASCII 双引号」这一类语法错误"
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="要扫描的目录或文件（默认 scripts src tests examples；相对路径按当前目录解析）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    roots = (
        [Path(p) for p in args.paths]
        if args.paths
        else [REPO / name for name in DEFAULT_ROOTS]
    )
    files = iter_python_files(roots)
    hits = scan_files(files)

    for shown, lineno, code in hits:
        print(f"SUSPECT {shown}:{lineno}")
        print(f"        {code}")
    print()
    print(f"扫描 {len(files)} 个文件｜可疑代码行 = {len(hits)}")
    print("（判据：非注释、不在三引号串内，出现「汉字+ASCII双引号+汉字」）")
    print("⚠️ 本脚本只列候选，**以 compile() 为准**。")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
