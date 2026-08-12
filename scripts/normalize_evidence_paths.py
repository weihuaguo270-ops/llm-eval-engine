"""Replace machine-specific workspace prefixes in committed evidence files."""

from __future__ import annotations

import argparse
from pathlib import Path


PREFIXES = (
    "D:\\\\agent_learning\\\\",
    "D:\\agent_learning\\",
    "D:/agent_learning/",
)
PLACEHOLDER = "${WORKSPACE_ROOT}/"


def normalize_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    normalized = text
    for prefix in PREFIXES:
        normalized = normalized.replace(prefix, PLACEHOLDER)
    if normalized == text:
        return False
    path.write_text(normalized, encoding="utf-8", newline="")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    changed = 0
    for raw in args.paths:
        path = Path(raw)
        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in {".json", ".md"}:
                changed += normalize_file(candidate)
    print(f"normalized {changed} evidence files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
