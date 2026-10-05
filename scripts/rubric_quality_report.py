"""Rubric 质量报告（甲·第一层）：**把 rubric 当被测对象**的纯计算指标。

与"评测集报告"的区别：这里不报 agent 的分数，只报**Rubric 本身**的质量信号：

1. **失败码覆盖**：每条条件的 `codes` 用了哪些、哪些从未触发（僵尸条件）、是否挤在一个码上（Rubric 太粗）
2. **判别力**：取值分布 / 是否退化 / 是否地板-天花板（全在 4–5）
3. **分歧归因**：把两人不一致的格分类——**Rubric 模糊** / **不判语义分歧** / **失败码分歧** / **材料不足** /
   **未标（不计入 Rubric 分歧）**
4. **冗余**：维度两两相关（高相关 = 两条在测同一件事）——**逐标注者分开算**，
   零方差与"无数据"分开报，``n < 15`` 不报 r（见 ``redundancy()``）
5. **兜底通道（BX）**：是否存在记录"Rubric 未覆盖"的 token——没有通道，就**量不出 Rubric 的缺口**

**三处已修（前两处是口径，第三处是控制流 bug；三处都曾让结论反向或丢信号）**：

- **未标 ≠ Rubric 分歧**：空值是**进度信号**。把"一人没填"算成"两人判得不一样"会让分歧数虚高——
  实测 129 格里 **110 格是未标**，真正的分档分歧只有 **5 格**，被完全淹没。
  `result_verdict.py` 已为此单列 `not_both`（注释写着「踩过」），本报告此前漏了这一步。
- **退化按「任一方恒定」判**：只看合并后的取值种类，**看不出"只有一方在变"**——
  实测把 `query_entity_validity` 报成"不退化"（3 种取值**全部来自 r1**），而门禁报"退化"（r2 恒定）。
  两处口径不一致正是本项目最警惕的错误类型（"两次口径不一致时比大小，会得出方向相反的结论"）。
  旧口径保留在 `degenerate_merged` 里备查，不删。
- **同分但归类不同被静默丢掉**：`codes` 比对原先放在 `a == b → continue` **之后**，
  于是"两人给同一档、但失败码不同"的格**根本不进报告**——与 docstring 原意
  （「分档相同与否先不论，归类不同」）相反。已改为**先比归类、再比档位**。
  这类分歧恰恰最该暴露：**严重度一致、归因不一致**——而失败码正是可诊断性的载体。
- **冗余**：旧实现把「n 不够」与「零方差」都报成 ``r=None``（读的人会当成"没有相关性"），
  又会把 **n=6** 的 ``r=0.845`` 当结论报出来（实测 10 对里有 3 对共用同一批 6 个格）。
  现改为**逐标注者分开算**、零方差与无数据分开报、``n < 15`` 不报 r——
  与 κ「要求双方都有变异」是**同一条纪律**。

**另外**：``code_channel_status()`` 把「失败码覆盖为空」的两种原因分开报——
「词表读不出来（算不了）」与「词表在、但一条码都没记录（**通道未启用**）」。
后者实测就是归档线的状态：**15 个声明码、触发 0 次**
（三个断点与修复见 ``reports/_revoked_20261003/FIX_20261005_code_channel.md``）。

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

#: 「未标」的归类名。**空值不是 Rubric 分歧**：它是进度信号。
#: 与 `verdict.py` 的 `blank` 保持同一口径——**只有空串算未标**；
#: `-` / `—` / `?` 属"有意的不可判"，不在此列。
BLANK_KIND = "未标（一人未填，不计入 Rubric 分歧）"

UNSCORED_SEPARATOR = "一人给了分、一人判不判（Rubric 边界不清 / 材料不足）"


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


def code_channel_status(coverage: dict[str, Any], spec_available: bool) -> dict[str, Any]:
    """判断「失败码」这条通道**有没有被行使过**——覆盖为空有两种截然不同的原因。

    这两种原因**必须分开报**，否则会把「通道没接通」读成「没有僵尸条件」：

    - 词表读不出来（规格缺失）→ ``无法计算``；
    - 词表在、但**一条码都没被记录** → ``**通道未启用**``（**不是**"所有码都健康"）。

    归档那条线的实测状态就是后者：**15 个声明码、触发 0 次**。根因是工作表文案写着
    「无需人工填」，而落盘路径只认人工填写的 ``code:`` —— 通道两端对不上
    （三个断点见 ``reports/_revoked_20261003/FIX_20261005_code_channel.md``）。
    """
    declared_total = sum(len(item.get("declared") or []) for item in coverage.values())
    recorded = sum(int(item.get("messages") or 0) for item in coverage.values())
    if not spec_available:
        verdict, exercised = "无法计算（受控词表读不出来）", False
    elif declared_total == 0:
        verdict, exercised = "受控词表为空", False
    elif recorded == 0:
        verdict = "**通道未启用**（一条失败码都没被记录 ≠ 没有僵尸条件）"
        exercised = False
    else:
        verdict, exercised = "通道已行使", True
    return {
        "declared_total": declared_total,
        "recorded": recorded,
        "channel_exercised": exercised,
        "verdict": verdict,
    }


def _distribution(values: list[float]) -> dict[int, int]:
    counter = Counter(values)
    return {int(k): v for k, v in sorted(counter.items())}


def discriminative_power(rows: list[dict[str, Any]], dimensions: tuple[str, ...]) -> dict[str, Any]:
    """判别力：取值分布 / 是否退化 / 地板-天花板占比。

    ``degenerate`` 采用 **κ 语境** 的定义：**任一方取值恒定**即算退化——一致性证据要求
    双方都有变异，只有一方在动的数据算不出有意义的 κ。

    旧定义（"合并后只有一种取值"）**看不出「只有一方在变」**，实测把
    ``query_entity_validity`` 报成 ``退化=False``，而门禁报 ``deg=True``。
    故对每方单列 ``by_rater``、旧值保留在 ``degenerate_merged`` 备查。

    **无数据的一方不算恒定**：一方完全没标是进度问题（由覆盖率反映），不是退化。
    """
    out: dict[str, Any] = {}
    for dim in dimensions:
        by_rater: dict[str, Any] = {}
        merged: list[float] = []
        for side in ("r1", "r2"):
            values: list[float] = []
            for row in rows:
                value = _numeric(row.get(f"{dim}__{side}"))
                if value is not None:
                    values.append(value)
            merged.extend(values)
            by_rater[side] = {
                "n": len(values),
                "distinct": len(set(values)),
                "distribution": _distribution(values),
            }
        counter = Counter(merged)
        flat_sides = [
            side for side, item in by_rater.items() if item["n"] and item["distinct"] <= 1
        ]
        out[dim] = {
            "n": len(merged),
            "distinct": len(counter),
            "distribution": _distribution(merged),
            "high_share": round(sum(v for k, v in counter.items() if k >= 4) / len(merged), 3) if merged else None,
            "by_rater": by_rater,
            "flat_sides": flat_sides,
            "degenerate": bool(flat_sides),
            "degenerate_merged": len(counter) <= 1,
        }
    return out


def null_token_channel() -> dict[str, Any]:
    """兜底通道检查：有没有能记录「Rubric 未覆盖」的 token（BX）。"""
    tokens = sorted(UNDECIDABLE_TOKENS)
    bx_like = [t for t in tokens if t in {"bx", "null", "none", "未覆盖", "其他"}]
    return {"null_tokens": tokens, "bx_like": bx_like, "has_bx_channel": bool(bx_like)}


def attribution(
    rows: list[dict[str, Any]], dimensions: tuple[str, ...], left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """分歧归因：把不一致的格分类，**并先把「未标」摘出去**。

    分类：Rubric 分档模糊 / 不判语义分歧 / 失败码分歧 / 材料不足（一人判不判）/ Rubric 未覆盖（兜底）/
    **未标（不计入 Rubric 分歧）**。

    返回里三个数各有用途，**不得混引**：
      - ``disagreements``：明细总格数（含未标，便于追溯）；
      - ``disagreements_excluding_blank``：**计入 Rubric 分歧的格数** ← 对外引用用这个；
      - ``blank_cells``：未标格数（进度信号）。
    """
    kinds: Counter = Counter()
    detail: list[dict[str, Any]] = []
    for row in rows:
        sample = str(row["id"])
        for dim in dimensions:
            a, b = _numeric(row.get(f"{dim}__r1")), _numeric(row.get(f"{dim}__r2"))
            raw_a = (row.get(f"{dim}__r1") or "").strip().lower()
            raw_b = (row.get(f"{dim}__r2") or "").strip().lower()
            codes_a = {c for c in ((left.get(sample) or {}).get(dim) or {}).get("codes") or []}
            codes_b = {c for c in ((right.get(sample) or {}).get(dim) or {}).get("codes") or []}
            if a is not None and b is not None:
                # 两人都给了分：**先比归类，再比档位**。本函数 docstring 原文即为
                # 「分档相同与否先不论，归类不同」——旧版把这段比对放在 `a == b → continue`
                # **之后**，于是"两人给同一档、但失败码不同"的格被**静默丢掉**，
                # 与注释意图相反。而那恰恰是本报告最该暴露的分歧：
                # **严重度一致、归因不一致**（可诊断性正是靠失败码承载的）。
                if a == b and codes_a == codes_b:
                    continue
                if codes_a != codes_b:
                    kind = "失败码分歧（分档相同与否先不论，归类不同）"
                else:
                    kind = "Rubric 分档模糊（两人都给了分但档位不同）"
            else:
                # 至少一方没有数值分。**先分清「未标」与「有意的不可判」**：
                # 两人给出同一个"不判"（都 na / 都 oos / 都没填）→ 一致，不是分歧。
                if a is None and b is None and raw_a == raw_b:
                    continue
                # 空值（未标）**不是 Rubric 分歧**：它是进度信号。把未标算成分歧会让分歧数虚高、
                # 把真正的分档分歧淹没（`result_verdict.py` 已为此单列 `not_both`）。
                if raw_a == "" or raw_b == "":
                    kind = BLANK_KIND
                elif a is not None or b is not None:
                    kind = UNSCORED_SEPARATOR
                elif {raw_a, raw_b} & {"na", "unattr", "oos"}:
                    # 两种"不判"不同（na vs unattr 等）→ 不判语义分歧；否则视为新情形
                    kind = "不判语义分歧（一人 na、一人 unattr/oos）"
                else:
                    kind = "兜底：Rubric 未覆盖的情形"
            kinds[kind] += 1
            detail.append({"sample": sample, "dim": dim, "r1": raw_a, "r2": raw_b, "kind": kind})
    # 未标格保留在明细里（可追溯），但**不进 Rubric 分歧的头条数字**；
    # 明细把未标排到最后，抽样才看得到真正的分歧长什么样。
    ordered = sorted(
        detail, key=lambda item: (item["kind"] == BLANK_KIND, item["sample"], item["dim"])
    )
    return {
        "kinds": dict(kinds),
        "disagreements": len(detail),
        "disagreements_excluding_blank": sum(v for k, v in kinds.items() if k != BLANK_KIND),
        "blank_cells": kinds.get(BLANK_KIND, 0),
        "blank_note": "「未标」= 该格没填，是进度信号，不计入 Rubric 分歧（同 result_verdict.py 的 not_both）",
        "detail": ordered[:20],
    }


#: 相关性可解读所需的最小完整格数。**与 `result_verdict.py` 的「可判格 < 15 只报计数」
#: 同一纪律**：n 太小时 r 的抽样误差大到无法解读，报出来只会被误引。
#: 量化依据（P2-4）：Efficient-HELM 的 Examples-Per-Scenario vs 95% CI of Rank Location
#: ——**10→±5、200→±2、1000→±1**。出处见 `docs/RUBRIC_EVAL_EXTERNAL_BENCHMARK.md` §2 附录 A。
#: 实测（归档批次）：10 对里有 3 对共用同一批 **6** 个格，却报出了 ``r=0.845``。
REDUNDANCY_MIN_N = 15


def _pearson(xs: list[float], ys: list[float]) -> tuple[Optional[float], bool]:
    """皮尔逊 r → ``(r, flat)``。

    ``flat=True`` **只表示"有数据、但某一侧零方差"**；数据不足时返回 ``(None, False)``。
    「无数据」与「零方差」必须分开：前者是进度问题，后者是**结论**
    （该维度没有变异 → 不可能与任何维度冗余）。同 ``discriminative_power`` 的纪律。
    """
    if len(xs) < 2:
        return None, False
    if len(set(xs)) <= 1 or len(set(ys)) <= 1:
        return None, True
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    if not vx or not vy:
        return None, True
    return round(cov / (vx * vy), 3), False


def redundancy(
    rows: list[dict[str, Any]],
    dimensions: tuple[str, ...],
    min_n: int = REDUNDANCY_MIN_N,
) -> dict[str, Any]:
    """维度两两相关——**逐标注者分开算**，并把「为什么没有 r / 能不能引用」写清楚。

    旧实现有三个毛病，每个都会让结论被误引：

    1. **``r=None`` 分不清原因**：n 不够 与 零方差 都返回 ``None``。零方差其实是**结论**
       （该维度没有信息 → 不可能与任何维度冗余），不是缺数据。
    2. **把两人分平均会掩盖「只有一方在变」**：这是本项目反复踩的同一类错误
       （同 ``discriminative_power`` 的 ``degenerate``，也同 κ「要求双方都有变异」）。
       故逐标注者各算一次，``by_rater`` 与 ``flat_sides`` 都给出；
       只有一方在变时，合并 r **只由单侧变异驱动，不可作为冗余证据**。
    3. **n 太小时的 r 会被当成结论**：实测 10 对里有 3 对共用同一批 6 个格。
       故 ``n < min_n`` 时不报 r、只报 n。

    每对返回：``n`` / ``r``（合并，仅供参考）/ ``by_rater`` / ``flat_sides`` /
    ``flat_merged`` / ``interpretable`` / ``reason``。
    """
    pairs: dict[str, Any] = {}
    for i, left in enumerate(dimensions):
        for right in dimensions[i + 1:]:
            xs_all: list[float] = []
            ys_all: list[float] = []
            by_rater: dict[str, Any] = {}
            flat_sides: list[str] = []
            for side in ("r1", "r2"):
                xs: list[float] = []
                ys: list[float] = []
                for row in rows:
                    a = _numeric(row.get(f"{left}__{side}"))
                    b = _numeric(row.get(f"{right}__{side}"))
                    if a is None or b is None:
                        continue
                    xs.append(a)
                    ys.append(b)
                r_side, flat_side = _pearson(xs, ys)
                if flat_side:
                    flat_sides.append(side)
                by_rater[side] = {
                    "n": len(xs),
                    "r": r_side if (r_side is not None and len(xs) >= min_n) else None,
                    "flat": flat_side,
                }
            for row in rows:
                a1, a2 = _numeric(row.get(f"{left}__r1")), _numeric(row.get(f"{left}__r2"))
                b1, b2 = _numeric(row.get(f"{right}__r1")), _numeric(row.get(f"{right}__r2"))
                if None in (a1, a2, b1, b2):
                    continue
                xs_all.append((a1 + a2) / 2)
                ys_all.append((b1 + b2) / 2)
            r_raw, flat_merged = _pearson(xs_all, ys_all)
            n = len(xs_all)
            if n == 0:
                interpretable = False
                reason = "无「两人都判」的共同格 → 无从计算（进度问题，不是相关性结论）"
            elif n < min_n:
                interpretable = False
                reason = f"n={n} < {min_n}：只报 n，不报 r（与「可判格 < 15 只报计数」同源）"
            elif flat_merged:
                interpretable = False
                if flat_sides:
                    reason = (
                        f"合并后零方差（{'、'.join(flat_sides)} 侧本身也无变异）→ "
                        "**合并口径测不出冗余**；该维度在这批数据上没有可用变异（这是结论，不是缺数据）"
                    )
                else:
                    reason = (
                        "合并后零方差，但**两侧各自都有变异**（典型原因：两人系统性反向）→ "
                        "合并口径不可测，只看逐方 r；本行不作为冗余证据"
                    )
            elif flat_sides:
                interpretable = False
                reason = (
                    f"{'、'.join(flat_sides)} 侧零方差：合并 r 只由**单侧**标注者的变异驱动，"
                    "**不可作为冗余证据**"
                )
            else:
                interpretable = True
                reason = ""
            pairs[f"{left}×{right}"] = {
                "n": n,
                "r": r_raw if n >= min_n else None,
                "by_rater": by_rater,
                "flat_sides": flat_sides,
                "flat_merged": flat_merged,
                "interpretable": interpretable,
                "reason": reason,
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
        "spec_available": condition is not None,
        "code_coverage": code_coverage(dimensions, [left, right]),
        "discriminative_power": discriminative_power(rows, dimensions),
        "bx_channel": null_token_channel(),
        "attribution": attribution(rows, dimensions, left, right),
        "redundancy": redundancy(rows, dimensions),
    }
    report["code_channel"] = code_channel_status(
        report["code_coverage"], bool(report["spec_available"])
    )
    out = args.out or args.batch / "rubric_quality.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== Rubric 质量报告：{args.batch.name}（维度 {list(dimensions)}）")
    print("\n[1] 失败码覆盖")
    if not report["spec_available"]:
        # **防静默降级**：规格读不出来时，`从未触发` 会显示为空，看起来像"没有僵尸条件"，
        # 实际是"根本没算"。必须显式说出来，否则这份报告会被误引。
        print("  ⚠️ 规格模块 `search_rubric_spec` 不可导入 → **本项无法计算**")
        print("     （`declared`/`从未触发` 为空 ≠ 没有僵尸条件，而是声明清单读不出来）")
    for dim, item in report["code_coverage"].items():
        print(f"  {dim:22} 触发 {item['messages']:2} 次｜从未触发 {item['never_triggered']}"
              f"｜最集中码占比 {item['top_share']}")
    channel = report["code_channel"]
    print(f"  通道：声明 {channel['declared_total']} 个码｜记录 {channel['recorded']} 次"
          f" → {channel['verdict']}")
    print("\n[2] 判别力（退化 = **任一方取值恒定**，κ 语境；无数据的一方不算恒定）")
    for dim, item in report["discriminative_power"].items():
        flat = "、".join(item["flat_sides"]) or "无"
        print(f"  {dim:22} n={item['n']:2}｜{item['distinct']} 个取值｜≥4 占 {item['high_share']}"
              f"｜退化={item['degenerate']}（恒定方：{flat}）")
        print(f"  {'':22} 逐方 r1 {item['by_rater']['r1']['distribution']}"
              f"｜r2 {item['by_rater']['r2']['distribution']}"
              f"｜合并口径退化={item['degenerate_merged']}")
    print(f"\n[3] 兜底通道（BX）: {'有' if report['bx_channel']['has_bx_channel'] else '**无**'}"
          f"｜tokens={report['bx_channel']['null_tokens']}")
    attr = report["attribution"]
    print("\n[4] 分歧归因")
    print(f"  明细合计 {attr['disagreements']} 格｜**计入 Rubric 分歧 {attr['disagreements_excluding_blank']} 格**"
          f"｜未标 {attr['blank_cells']} 格（{attr['blank_note']}）")
    for kind, count in sorted(attr["kinds"].items(), key=lambda kv: -kv[1]):
        print(f"  {count:2} 格  {kind}")
    print(f"\n[5] 维度冗余（皮尔逊 r；逐标注者分开算；n<{REDUNDANCY_MIN_N} 只报 n）")
    for pair, item in report["redundancy"].items():
        r_text = "—" if item["r"] is None else str(item["r"])
        flat = "、".join(item["flat_sides"]) or "无"
        sides = item["by_rater"]
        print(f"  {pair:44} 合并 n={item['n']:2} r={r_text}"
              f"｜r1 n={sides['r1']['n']:2} r={sides['r1']['r']}"
              f"｜r2 n={sides['r2']['n']:2} r={sides['r2']['r']}"
              f"｜零方差：{flat}")
        if not item["interpretable"]:
            print(f"  {'':44} ↳ {item['reason']}")
    print(f"\n[written] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
