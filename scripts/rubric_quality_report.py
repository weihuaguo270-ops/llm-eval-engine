"""Rubric 质量报告（甲·第一层）：**把 rubric 当被测对象**的纯计算指标。

与"评测集报告"的区别：这里不报 agent 的分数，只报**判据本身**的质量信号：

1. **失败码覆盖**：每条条件的 `codes` 用了哪些、哪些从未触发（僵尸判据）、是否挤在一个码上（判据太粗）
2. **判别力**：取值分布 / 是否退化 / 是否地板-天花板（全在 4–5）
3. **分歧归因**：把两人不一致的格分类——**判据模糊** / **不判语义分歧** / **失败码分歧** / **材料不足**
4. **冗余**：维度两两相关（高相关 = 两条在测同一件事）
5. **兜底通道（BX）**：是否存在记录"判据未覆盖"的 token——没有通道，就**量不出 rubric 的缺口**

用法::

    python scripts/rubric_quality_report.py --batch reports/search-live
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

from eval_engine.core.verdict import UNDECIDABLE_TOKENS  # noqa: E402

# 指标逻辑是通用的；「失败码声明」来自那条线的规格，线撤销后规格不在 → 做成可选。
try:  # pragma: no cover
    from eval_engine.core.search_rubric_spec import condition  # type: ignore
except Exception:
    condition = None  # type: ignore


def _cells(batch: Path, rater: str) -> dict[str, Any]:
    path = batch / f"cells_{rater}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _numeric(value: Any) -> Optional[float]:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 1.0 <= number <= 5.0 else None


def code_coverage(dimensions: tuple[str, ...], sidecars: list[dict[str, Any]]) -> dict[str, Any]:
    """失败码覆盖：用了哪些码、哪些从未触发、是否挤在一个码上。"""
    used: dict[str, Counter] = {d: Counter() for d in dimensions}
    for side in sidecars:
        for _sample, cells in side.items():
            for dim, payload in (cells or {}).items():
                if dim not in used:
                    continue
                for code in (payload or {}).get("codes") or []:
                    used[dim][code] += 1
    report: dict[str, Any] = {}
    for dim in dimensions:
        declared = [c.code for c in condition(dim).codes] if condition else []
        counts = used[dim]
        total = sum(counts.values())
        report[dim] = {
            "declared": declared,
            "used": dict(counts),
            "never_triggered": [c for c in declared if c not in counts],
            "messages": total,
            "top_share": (max(counts.values()) / total) if total else None,
        }
    return report


def discriminative_power(rows: list[dict[str, Any]], dimensions: tuple[str, ...]) -> dict[str, Any]:
    """判别力：有多少个不同取值、是否退化、地板-天花板占比（两人合并看）。"""
    out: dict[str, Any] = {}
    for dim in dimensions:
        values = [v for row in rows for v in (_numeric(row.get(f"{dim}__r1")), _numeric(row.get(f"{dim}__r2"))) if v]
        counter = Counter(values)
        out[dim] = {
            "n": len(values),
            "distinct": len(counter),
            "distribution": {int(k): v for k, v in sorted(counter.items())},
            "high_share": round(sum(v for k, v in counter.items() if k >= 4) / len(values), 3) if values else None,
            "degenerate": len(counter) <= 1,
        }
    return out


def null_token_channel() -> dict[str, Any]:
    """兜底通道检查：有没有能记录「判据未覆盖」的 token（BX）。"""
    tokens = sorted(UNDECIDABLE_TOKENS)
    bx_like = [t for t in tokens if t in {"bx", "null", "none", "未覆盖", "其他"}]
    return {"null_tokens": tokens, "bx_like": bx_like, "has_bx_channel": bool(bx_like)}


def attribution(
    rows: list[dict[str, Any]], dimensions: tuple[str, ...], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """分歧归因：把不一致的格分成四类。"""
    kinds: Counter = Counter()
    detail: list[dict[str, Any]] = []
    for row in rows:
        sample = str(row["id"])
        for dim in dimensions:
            a, b = _numeric(row.get(f"{dim}__r1")), _numeric(row.get(f"{dim}__r2"))
            raw_a = (row.get(f"{dim}__r1") or "").strip().lower()
            raw_b = (row.get(f"{dim}__r2") or "").strip().lower()
            if a is not None and b is not None:
                if a == b:
                    continue
                kind = "判据分档模糊（两人都给了分但档位不同）"
            elif a is None and b is None:
                if raw_a == raw_b:
                    continue
                # 两种"不判"不同（na vs unattr 等）→ 不判语义分歧；否则视为新情形
                kind = (
                    "不判语义分歧（一人 na、一人 unattr/oos）"
                    if {raw_a, raw_b} & {"na", "unattr", "oos"} and raw_a != raw_b
                    else "兜底：判据未覆盖的情形"
                )
            else:
                kind = "一人给了分、一人判不判（判据边界不清 / 材料不足）"
            codes_a = {c for c in ((left.get(sample) or {}).get(dim) or {}).get("codes") or []}
            codes_b = {c for c in ((right.get(sample) or {}).get(dim) or {}).get("codes") or []}
            if a is not None and b is not None and codes_a != codes_b:
                kind = "失败码分歧（分档相同与否先不论，归类不同）"
            kinds[kind] += 1
            detail.append({"sample": sample, "dim": dim, "r1": raw_a, "r2": raw_b, "kind": kind})
    return {"kinds": dict(kinds), "disagreements": len(detail), "detail": detail[:20]}


def redundancy(rows: list[dict[str, Any]], dimensions: tuple[str, ...]) -> dict[str, Any]:
    """维度两两相关（仅在两人都判的格上算皮尔逊相关，无需 numpy）。"""
    pairs: dict[str, Any] = {}
    for i, left in enumerate(dimensions):
        for right in dimensions[i + 1:]:
            xs: list[float] = []
            ys: list[float] = []
            for row in rows:
                a1, a2 = _numeric(row.get(f"{left}__r1")), _numeric(row.get(f"{left}__r2"))
                b1, b2 = _numeric(row.get(f"{right}__r1")), _numeric(row.get(f"{right}__r2"))
                if None in (a1, a2, b1, b2):
                    continue
                xs.append((a1 + a2) / 2)
                ys.append((b1 + b2) / 2)
            if len(xs) < 4:
                pairs[f"{left}×{right}"] = {"n": len(xs), "r": None}
                continue
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            vx = sum((x - mx) ** 2 for x in xs) ** 0.5
            vy = sum((y - my) ** 2 for y in ys) ** 0.5
            pairs[f"{left}×{right}"] = {
                "n": len(xs),
                "r": round(cov / (vx * vy), 3) if vx and vy else None,
            }
    return pairs


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rubric 质量报告（第一层：纯计算）")
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    index = json.loads((args.batch / "search_steps.json").read_text(encoding="utf-8"))
    dimensions = tuple(index["meta"].get("dimensions") or ())
    rows: list[dict[str, Any]] = []
    for name in ("scores_r1.csv", "scores_r2.csv"):
        path = args.batch / name
        suffix = "r1" if "r1" in name else "r2"
        if not path.exists():
            continue
        for record in csv.DictReader(path.open(encoding="utf-8-sig")):
            sample = str(record.get("id") or "").strip()
            target = next((r for r in rows if r["id"] == sample), None)
            if target is None:
                target = {"id": sample}
                rows.append(target)
            for dim in dimensions:
                target[f"{dim}__{suffix}"] = record.get(dim)

    left, right = _cells(args.batch, "r1"), _cells(args.batch, "r2")
    report = {
        "batch": str(args.batch),
        "dimensions": list(dimensions),
        "code_coverage": code_coverage(dimensions, [left, right]),
        "discriminative_power": discriminative_power(rows, dimensions),
        "bx_channel": null_token_channel(),
        "attribution": attribution(rows, dimensions, left, right),
        "redundancy": redundancy(rows, dimensions),
    }
    out = args.out or args.batch / "rubric_quality.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== Rubric 质量报告：{args.batch.name}（维度 {list(dimensions)}）")
    print("\n[1] 失败码覆盖")
    for dim, item in report["code_coverage"].items():
        print(f"  {dim:22} 触发 {item['messages']:2} 次｜从未触发 {item['never_triggered']}"
              f"｜最集中码占比 {item['top_share']}")
    print("\n[2] 判别力")
    for dim, item in report["discriminative_power"].items():
        print(f"  {dim:22} n={item['n']:2}｜{item['distinct']} 个取值｜≥4 占 {item['high_share']}"
              f"｜退化={item['degenerate']}｜分布 {item['distribution']}")
    print(f"\n[3] 兜底通道（BX）: {'有' if report['bx_channel']['has_bx_channel'] else '**无**'}"
          f"｜tokens={report['bx_channel']['null_tokens']}")
    print("\n[4] 分歧归因")
    for kind, count in sorted(report["attribution"]["kinds"].items(), key=lambda kv: -kv[1]):
        print(f"  {count:2} 格  {kind}")
    print("\n[5] 维度冗余（皮尔逊 r，n≥4）")
    for pair, item in report["redundancy"].items():
        print(f"  {pair:44} r={item['r']} (n={item['n']})")
    print(f"\n[written] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
