"""结果判断（② 被测对象好不好）：把分数变成**判定**，并算出**缺陷率**（带按请求聚簇 CI）。

与 `build`（① 评测集质量：κ/可判率）**并列输出、互不冒名**：

    ① 评测集质量：κ + 按请求聚簇 CI + 可判率      → 「这批数能不能下结论」
    ② 被测对象表现：缺陷率（按请求聚簇 CI）        → 「agent 表现如何」
    ③ 不可判率 / 未标率                          → 必须进结论（不可判率本身就是结论）

判定规则来自 `search_step.VERDICT_BANDS`（合格线：4–5 合格 / 3 边缘 / 1–2 缺陷 /
na·unattr·oos 不可判 / 空 未标）。**分歧不抹平**：两人判定不同时单列为 `disagree`，
只对"两人一致"的格算缺陷率，并同时报出分歧率。

用法::

    python scripts/result_verdict.py --batch reports/search-live [--dimension fallback_behavior]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
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

from eval_engine.core.verdict import (  # noqa: E402
    MIN_JUDGED_FOR_RATE,
    bands_identity,
    clustered_rate_ci,
    load_bands,
    load_bands_document,
    verdict_for,
)

#: 「可判格 < N 只报计数」的阈值**定义在 `core.verdict`**（`MIN_JUDGED_FOR_RATE`，见上方的 import）——
#: 发布门禁消费判定结果时要用同一个数，而**一个数只能有一个定义处**（否则又是两个口径）。
#: 外部量化依据（Efficient-HELM 的 Examples-Per-Scenario ↔ CI 宽度）与出处见该常量处的注释。


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="结果判断：缺陷率（带聚簇 CI）")
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--dimension", default=None, help="只报某一维（默认全部）")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--bands", type=Path, default=None,
        help="合格线表 JSON（默认 <batch>/verdict_bands.json；缺则判定为 unbanded）",
    )
    parser.add_argument(
        "--expect-bands-sha256", default=None,
        help="预期合格线身份（前缀即可）。不符则退出码 3（P2：读取端软校验）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    index = json.loads((args.batch / "search_steps.json").read_text(encoding="utf-8"))
    bands_path = args.bands or (args.batch / "verdict_bands.json")
    # 维度层交给判定；整份文档留给口径出处。
    # 【P3-3】出处必须**打出来**：`load_bands` 只取维度层，外壳里的 `note` / `rulings_version`
    # 会被丢掉——而「**这份合格线是重建版**」正写在 `note` 里。补回那处**透明度回退**。
    # 【P0】这里原本自带一段读原始 JSON 的逻辑（同一概念的**第三份**读法），现统一走
    # `load_bands_document`：一份文件只有一种读法。
    bands = load_bands(bands_path)
    document = load_bands_document(bands_path)
    bands_meta: dict[str, Any] = {
        key: document[key]
        for key in ("note", "rulings_version", "convention", "provenance", "derivation")
        if key in document
    }
    # 【P1】合格线**内容身份**；【P2】起：身份不可识别/不符会改**退出码**，但**不改判定结果**。
    identity = bands_identity(bands_path)
    dimensions = tuple(index["meta"].get("dimensions") or ())
    if args.dimension:
        dimensions = (args.dimension,)
    case_of: dict[str, str] = {
        str(s["sample_id"]): str(s["case_id"]) for s in index.get("samples") or []
    }

    sheets: dict[str, dict[str, str]] = {}
    for rater in ("r1", "r2"):
        path = args.batch / f"scores_{rater}.csv"
        if path.exists():
            sheets[rater] = {
                str(row["id"]).strip(): row
                for row in csv.DictReader(path.open(encoding="utf-8-sig"))
            }

    verdicts: dict[str, dict[str, str]] = {}
    for rater, rows in sheets.items():
        verdicts[rater] = {
            sample: {dim: verdict_for(dim, row.get(dim), bands) for dim in dimensions}
            for sample, row in rows.items()
        }

    report: dict[str, Any] = {
        "batch": str(args.batch), "dimensions": list(dimensions),
        "bands_loaded": bool(bands), "bands_meta": bands_meta,
        # 【P1】身份随数字走：数字离开这份报告时，读者仍能知道它依赖哪一份合格线
        "bands_identity": identity, "by_dimension": {},
    }
    for dim in dimensions:
        band = bands.get(dim, {})
        defect_by_case: dict[str, int] = defaultdict(int)
        total_by_case: dict[str, int] = defaultdict(int)
        counts: Counter = Counter()
        for sample, case in case_of.items():
            pair = [
                verdicts[r].get(sample, {}).get(dim)
                for r in ("r1", "r2")
                if sample in verdicts[r]
            ]
            # **只有两人都真的判了才进入判定**：一方空（按 scope 未判 / 未填）→ `not_both`。
            # 踩过：把"按设计未判"算成 `disagree` → 分歧数虚高（把 scope 政策误报成 Rubric 分歧）。
            if len(pair) < 2 or any(m in (None, "", "blank") for m in pair):
                counts["not_both"] += 1
                continue
            total_by_case[case] += 1
            if pair[0] == pair[1]:
                counts[str(pair[0])] += 1
                if pair[0] == "defect":
                    defect_by_case[case] += 1
            else:
                counts["disagree"] += 1
        judged = sum(v for k, v in counts.items() if k in ("pass", "marginal", "defect"))
        defects = counts.get("defect", 0)
        low, high = clustered_rate_ci(defect_by_case, total_by_case)
        report["by_dimension"][dim] = {
            "defect_definition": band.get("defect"),
            "counts": dict(counts),
            "judged_cells": judged,
            "defect_rate": round(defects / judged, 3) if judged else None,
            "defect_rate_ci": [None if low != low else round(low, 3), None if high != high else round(high, 3)],
        }

    print(f"=== 结果判断：{args.batch.name}（维度 {list(dimensions)}）")
    print("> 判定规则：4–5 合格｜3 边缘｜1–2 缺陷｜na/unattr/oos 不可判｜空/未同判 不计入判定")
    print(f"> **纪律**：可判格 < {MIN_JUDGED_FOR_RATE} 时**只报计数、不报率**"
          f"（与「n<5 不引用 κ」同源；量化依据见模块头 MIN_JUDGED_FOR_RATE 注释）\n")
    if not bands:
        # **防静默降级**：合格线读不出来时，每一维都会判成 `unbanded`、缺陷率全 0。
        # 不看输出的读者会把「没算」读成「零缺陷」（实测踩过：外层结构不符导致全表 unbanded）。
        print("⚠️ 未加载到任何合格线 → 下面每一维都会是 `unbanded`、缺陷率全 0。")
        print(f"   **这不是「零缺陷」，是「没算」**。请检查 --bands：{bands_path}\n")
    for key, value in bands_meta.items():
        # 口径出处（含"这是重建版"这类自我声明）必须随数字一起出现
        print(f"> 口径[{key}]：{value}")
    if identity["recognized"]:
        print(f"> 合格线身份：{identity['algo']}｜`{identity['sha256'][:16]}`"
              f"（{len(identity['dimensions'])} 维：{'、'.join(identity['dimensions'])}）")
    else:
        print(f"> 合格线身份：**不可识别**（{identity['reason']}）"
              "—— 下面每一维都会落成 `unbanded`，**这不是「零缺陷」**")
    for dim, item in report["by_dimension"].items():
        judged = item["judged_cells"]
        print(f"[{dim}]")
        print(f"   缺陷定义：{item['defect_definition']}")
        print(f"   判定计数：{item['counts']}")
        if judged >= MIN_JUDGED_FOR_RATE:
            print(f"   可判格 {judged}｜**缺陷率** {item['defect_rate']}"
                  f"（95% CI {item['defect_rate_ci']}，按请求聚簇）")
        else:
            print(f"   可判格 {judged}（< {MIN_JUDGED_FOR_RATE}）→ **只报计数**："
                  f"缺陷 {item['counts'].get('defect', 0)} 个"
                  f"｜率不可引用（分母过小，点估计与聚簇 CI 会对不上）")
    out = args.out or args.batch / "result_verdict.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[written] {out}")

    # 【P2】读取端**软校验**：产物**先落盘**（快照不可再采集 → 报告必须留下），
    # **告警只走退出码**——这是本仓采集侧 P0-2 已经用过的同一条纪律。
    # 本步**不改门禁**：门禁接入是计划 P3。
    if not identity["recognized"]:
        print(f"\n❌ 合格线**不可识别**（{identity['reason']}）→ 退出码 2")
        print("   上面的判定会全落成 `unbanded`——**这不是「零缺陷」，是「没算」**")
        return 2
    if args.expect_bands_sha256 and not identity["sha256"].startswith(args.expect_bands_sha256):
        print("\n❌ 合格线身份与预期不符 → 退出码 3")
        print(f"   预期（前缀）：{args.expect_bands_sha256}")
        print(f"   实际：        {identity['sha256']}（{identity['algo']}）")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
