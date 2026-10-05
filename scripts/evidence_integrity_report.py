"""证据完整性报告：**这批数据能不能用、该带什么限定**。

与另两个报告的分工（**互不冒名**）：

    ① `rubric_quality_report.py` —— **判据本身**的质量（失败码覆盖 / 判别力 / 分歧归因 / 冗余）
    ② `result_verdict.py`       —— **被测对象**的表现（缺陷率 + 按请求聚簇 CI）
    ③ 本脚本                     —— **证据本身**的完整性

**六项**检查（每一项都来自本项目**实测踩过的坑**）：

1. **失败成簇**（P1-1）：把 N 条失败样本还原成"实际来自几个请求、几个事故窗口"。
   独立单位是**请求／事故**，不是样本——实测 25 条 `tool_error` 只来自 **16 个请求**、
   集中在 **2 个时间窗**（相隔约 13 小时）。**报 25/80 = 36% 会严重高估证据量。**
2. **快照寿期**（P1-3）：不可再采集的证据必须有"何时该复核/降级引用"的声明
   （仿 FreshQA 的"预计下次复核日期"）。本栏**不可重采**，故到期只能**降级或作废**，
   字段名因此用 `review_by` 而不是 `expires_at`。
3. **meta 对账**：`meta.outcome_strata` 与样本**真实取值**是否一致
   （曾因硬编码 `("success","failure")` 两个键，静默丢掉 29 行）。
4. **覆盖报告**：采集时的覆盖率门禁结论在不在（`collection_coverage.json`，P0-2 的产物）。
5. **来源集中度**（P2-3）：请求的检索证据来自几个域名。**0 域名（证据缺失）与 1 域名（单一来源）
   必须分开**——混成一个数就重犯本项目「两个口径混成一个数」的经典错误。**仅作 triage 信号**：
   快照已冻结，「拒绝」已不可能。
6. **拒绝留档**（P2-1）：`rejection_ledger.json` 在不在、按类别各多少。

**本脚本只报告、不判定门禁，故一律退出 0**——门禁在采集侧（P0-2）。
它要回答的是"引用这批数时**必须带哪些限定**"。

用法::

    python scripts/evidence_integrity_report.py --batch reports/search-live
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass


def _parse_stamp(text: Any) -> Optional[float]:
    """解析时间串为 epoch 秒；**解析不了返回 None（不猜）**。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(raw, fmt))
        except (ValueError, OverflowError):
            continue
    return None


def group_windows(stamps: list[float], window_minutes: float = 30.0) -> list[list[float]]:
    """把时间戳聚成"事故窗口"：**相邻间隔 > window_minutes 即开新窗**。

    为什么**不**按钟表对齐分桶（如"整点/半小时"）：事故长度不由钟表决定。
    用相邻间隔切分，同一次事故（实测 10:07–10:12，最大间隔约 2 分钟）会落进同一个窗口，
    而相隔 13 小时的两次事故必然被分开。
    """
    ordered = sorted(stamp for stamp in stamps if stamp is not None)
    windows: list[list[float]] = []
    for stamp in ordered:
        if windows and (stamp - windows[-1][-1]) <= window_minutes * 60:
            windows[-1].append(stamp)
        else:
            windows.append([stamp])
    return windows


def failure_clusters(
    samples: list[dict[str, Any]],
    *,
    field: str = "outcome_stratum",
    values: tuple[str, ...] = ("tool_error",),
    window_minutes: float = 30.0,
) -> dict[str, Any]:
    """把失败样本还原成**实际独立单位**：几个请求、几个事故窗口。

    这是本脚本最重要的一项：`n_samples` 从来不是独立单位，
    但报告里最容易被当成独立单位的就是它。
    """
    failing = [s for s in samples if str(s.get(field)) in values]
    by_request: dict[str, int] = {}
    by_provenance: dict[str, int] = {}
    for sample in failing:
        key = str(sample.get("case_id"))
        by_request[key] = by_request.get(key, 0) + 1
        prov = str(sample.get("provenance"))
        by_provenance[prov] = by_provenance.get(prov, 0) + 1

    stamps = [_parse_stamp(s.get("collected_at")) for s in failing]
    windows = group_windows([s for s in stamps if s is not None], window_minutes)
    window_rows = []
    for window in windows:
        window_rows.append(
            {
                "start": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(window[0])),
                "end": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(window[-1])),
                "n_samples": len(window),
                "span_minutes": round((window[-1] - window[0]) / 60, 1),
            }
        )
    windows_sorted = sorted(window_rows, key=lambda row: -row["n_samples"])
    return {
        "field": field,
        "values": list(values),
        "n_failing_samples": len(failing),
        "n_requests": len(by_request),
        "n_windows": len(windows),
        "max_samples_per_request": max(by_request.values()) if by_request else 0,
        "max_samples_per_window": max((row["n_samples"] for row in window_rows), default=0),
        "by_request": dict(sorted(by_request.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_provenance": by_provenance,
        "windows": windows_sorted,
        "independent_units_note": (
            f"{len(failing)} 条失败样本实际只来自 **{len(by_request)} 个请求**、"
            f"**{len(windows)} 个时间窗**（窗口阈值 {window_minutes:g} 分钟）。"
            "引用失败率时，独立单位是**请求／事故**而非样本；"
            "按样本报会把它放大数倍。"
        ),
    }


def snapshot_freshness(
    out_dir: Path,
    samples: list[dict[str, Any]],
    *,
    review_interval_days: int = 90,
    today: Optional[str] = None,
) -> dict[str, Any]:
    """快照寿期：**优先用快照清单里声明的 policy**，没有才按 CLI 间隔推算并标注来源。

    为什么要分"声明/推算"：本项目曾多次因"两个口径混在一个数里"而出错。
    声明值来自采集当时的策略（冻结），推算值来自今天的 CLI 参数（会漂移）——
    两者含义不同，**必须分开报**。
    """
    today = today or time.strftime("%Y-%m-%d")
    today_stamp = _parse_stamp(today)

    entries: list[dict[str, Any]] = []
    manifest_path = out_dir / "snapshots_manifest.json"
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        raw = payload.get("snapshots") if isinstance(payload, dict) else None
        if isinstance(raw, list):
            entries = [row for row in raw if isinstance(row, dict)]
    if not entries:  # 清单不可用 → 退回样本身份表
        seen: dict[str, dict[str, Any]] = {}
        for sample in samples:
            sid = str(sample.get("snapshot_id") or "")
            if sid and sid not in seen:
                seen[sid] = {"snapshot_id": sid, "collected_at": sample.get("collected_at")}
        entries = list(seen.values())

    rows: list[dict[str, Any]] = []
    source_counts = {"declared": 0, "derived": 0, "unknown": 0}
    for entry in entries:
        policy = entry.get("snapshot_policy")
        policy = policy if isinstance(policy, dict) else {}
        collected = _parse_stamp(entry.get("collected_at"))
        declared = str(policy.get("review_by") or "").strip()
        due_stamp = _parse_stamp(declared)
        source = "unknown"
        if due_stamp is not None:
            source = "declared"
        elif collected is not None:
            due_stamp = collected + review_interval_days * 86400
            source = "derived"
        source_counts[source] += 1
        days_left = None
        if due_stamp is not None and today_stamp is not None:
            days_left = round((due_stamp - today_stamp) / 86400, 1)
        rows.append(
            {
                "snapshot_id": entry.get("snapshot_id"),
                "collected_at": entry.get("collected_at"),
                "review_by": time.strftime("%Y-%m-%d", time.localtime(due_stamp)) if due_stamp else "",
                "policy_source": source,
                "recollectable": policy.get("recollectable"),
                "days_left": days_left,
                "overdue": bool(days_left is not None and days_left < 0),
            }
        )

    overdue = [row for row in rows if row["overdue"]]
    return {
        "today": today,
        "review_interval_days": review_interval_days,
        "n_snapshots": len(rows),
        "policy_source_counts": source_counts,
        "n_overdue": len(overdue),
        "overdue": overdue[:20],
        "oldest": min((row["collected_at"] for row in rows if row["collected_at"]), default=None),
        "newest": max((row["collected_at"] for row in rows if row["collected_at"]), default=None),
        "note": (
            "本栏**不可再采集**：到期后只能**降级引用或作废**，不能「重采一次」。"
            "`policy_source=derived` 表示该份快照没有声明寿期，此处按 CLI 间隔推算——"
            "**推算值随参数漂移，引用时须写明用的是哪一档**。"
        ),
    }


def reconcile_outcome_strata(
    meta: dict[str, Any], samples: list[dict[str, Any]]
) -> dict[str, Any]:
    """`meta.outcome_strata` 与样本**真实取值**对账。

    对账不上就是"统计口径与真实取值不一致且静默"——本项目已因此丢过 29 行。
    """
    declared = meta.get("outcome_strata")
    declared = declared if isinstance(declared, dict) else {}
    actual: dict[str, int] = {}
    for sample in samples:
        key = str(sample.get("outcome_stratum"))
        actual[key] = actual.get(key, 0) + 1
    actual = dict(sorted(actual.items(), key=lambda kv: (-kv[1], kv[0])))
    return {
        "declared": declared,
        "declared_total": sum(declared.values()) if declared else 0,
        "actual": actual,
        "actual_total": sum(actual.values()),
        "n_samples": len(samples),
        "consistent": dict(declared) == actual,
        "missing_from_meta": {k: v for k, v in actual.items() if k not in declared},
    }


def coverage_report_state(out_dir: Path) -> dict[str, Any]:
    """采集时的覆盖率门禁结论在不在（`collection_coverage.json`）。"""
    path = out_dir / "collection_coverage.json"
    if not path.exists():
        return {
            "present": False,
            "note": "无覆盖率报告——**该批次早于 P0-2 门禁**，或采集未走门禁路径。",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"present": True, "readable": False, "error": str(exc)}
    return {
        "present": True,
        "readable": True,
        "ok": payload.get("ok"),
        "problems": payload.get("problems") or [],
        "empty_strata": payload.get("empty_strata") or [],
        "zero_sample_requests": payload.get("zero_sample_requests") or [],
    }


_URL_RE = re.compile(r"https?://([^/\s\"'<>)]+)")


def _domains_of(text: str) -> set[str]:
    """抽出域名，并**去掉 `www.` 前缀**（`www.a.example.com` 与 `a.example.com` 视为同一站点）。

    不做这一步，同一个站点的两种写法会被当成两个来源——那就把"单一来源"误判成"多来源"。
    """
    out: set[str] = set()
    for host in _URL_RE.findall(text or ""):
        host = host.lower()
        out.add(host[4:] if host.startswith("www.") else host)
    return out


def source_concentration(
    samples: list[dict[str, Any]], *, min_domains: int = 2
) -> dict[str, Any]:
    """来源集中度（P2-3，借 SimpleQA 的「域名去重后 <2 个唯一域名则弃用」）。

    ⚠️ **必须把两种「域名数少」分开**——它们是**完全不同的东西**：

    - ``no_evidence``：**抽不到任何 URL** → 证据缺失（与 `tool_error` 同源）；
    - ``single_source``：有证据、但只来自**一个**域名 → SimpleQA 规则真正的对象。

    混成一个数，就重犯本项目反复记录的那类错误（"两个口径混成一个数"）。
    实测（归档批次）：**0 域名 23 个 / 恰好 1 个 12 个 / ≥2 个 14 个**——
    规则直接搬会命中 35/49 = 71%，其中 23 个其实是"根本没检索到东西"。

    ⚠️ **它只能是 triage 信号，不能是拒绝规则**：本栏采集后**快照已冻结**，
    「拒绝」已不可能（SimpleQA 是在**出题时**用这条规则筛题）。它的用途是提示：
    这条请求的取值只有单一来源支撑，引用其「有据」时须限定。

    ⚠️ 域名从 **`observation`** 抽，**不是** `sources`——后者记的是
    「样本来自哪个请求/变体」，不含 URL（实测归档批次 80/80 样本皆如此）。
    """
    per_case: dict[str, set[str]] = {}
    for sample in samples:
        case = str(sample.get("case_id"))
        per_case.setdefault(case, set()).update(
            _domains_of(str(sample.get("observation") or ""))
        )
    buckets: dict[str, list[str]] = {"no_evidence": [], "single_source": [], "multi_source": []}
    for case, domains in per_case.items():
        if not domains:
            buckets["no_evidence"].append(case)
        elif len(domains) < min_domains:
            buckets["single_source"].append(case)
        else:
            buckets["multi_source"].append(case)
    return {
        "min_domains": min_domains,
        "n_requests": len(per_case),
        "counts": {key: len(value) for key, value in buckets.items()},
        "no_evidence": sorted(buckets["no_evidence"]),
        "single_source": sorted(buckets["single_source"]),
        "multi_source": sorted(buckets["multi_source"]),
        "domains_by_request": {case: sorted(d) for case, d in sorted(per_case.items())},
        "note": (
            "`no_evidence`（0 域名）是**证据缺失**，与 `single_source`（1 域名）不是一回事；"
            "两者都不得与 `multi_source` 合成一个比例。本项仅作 triage 信号——"
            "**快照已冻结，「拒绝」已不可能**，它只用于限定引用的强度。"
        ),
    }


def rejection_ledger_state(out_dir: Path) -> dict[str, Any]:
    """拒绝留档在不在（P2-1 的活侧检查）。"""
    path = out_dir / "rejection_ledger.json"
    if not path.exists():
        return {
            "present": False,
            "note": "无拒绝留档——**该批次早于 P2-1**，或采集未走留档路径。",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"present": True, "readable": False, "error": str(exc)}
    return {
        "present": True,
        "readable": True,
        "counts_by_category": payload.get("counts_by_category") or {},
        "n_entries": len(payload.get("entries") or []),
        "not_visible_here": sorted((payload.get("not_visible_here") or {})),
    }


#: 上游记录器的截断上限（**上游事实，不是本仓设置**）：thought / observation 各 500 字、
#: final_answer 1000 字、工具 arguments 300 字。出处：工作表 `data_note` 与 v14 快照 §6。
DEFAULT_TRUNCATION_LIMITS = {"observation": 500, "final_answer": 1000}


def truncation_evidence(
    samples: list[dict[str, Any]], *, limits: Optional[dict[str, int]] = None
) -> dict[str, Any]:
    """材料截断的**下界估计**（P3-1）。

    为什么要测：`citation_grounding` 的可判率只有 **2%**（v14 快照 §6），
    根因不是口径分歧，而是**上游记录器把工具返回截断到 500 字**——
    引用对不上任何可见材料时，**分不清「这条引用是假的」还是「材料被截掉了」**。

    怎么测：数**长度恰好达到上限**的样本。达到上限 ⇒ 被截断；未达到 ⇒ 不能说明任何事。
    故这是一个**下界**，不是截断率本身。

    ⚠️ **本仓修不了**：上限在 react-agent 的记录器里。要解，得改上游并**重新采集**——
    而 `live_snapshot` 分栏**不可再采集** ⇒ 历史批次的这一限制**永久存在**。
    """
    limits = dict(limits or DEFAULT_TRUNCATION_LIMITS)
    total = len(samples)
    by_field: dict[str, Any] = {}
    for field, limit in limits.items():
        lengths = [len(str(sample.get(field) or "")) for sample in samples]
        at_limit = [
            str(sample.get("case_id"))
            for sample in samples
            if len(str(sample.get(field) or "")) >= limit
        ]
        by_field[field] = {
            "limit": limit,
            "at_limit_samples": len(at_limit),
            "at_limit_share": round(len(at_limit) / total, 3) if total else None,
            "max_length": max(lengths) if lengths else 0,
            "example_cases": sorted(set(at_limit))[:10],
        }
    return {
        "n_samples": total,
        "by_field": by_field,
        "note": (
            "`at_limit_*` 是**下界**：长度恰好等于上限 ⇒ 被截断；小于上限不能说明任何事。"
            "上限在上游记录器里，**本仓修不了**；`live_snapshot` 不可再采集 ⇒ "
            "历史批次的这一限制**永久存在**。"
        ),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="证据完整性报告（失败成簇 / 快照寿期 / meta 对账 / 覆盖报告）")
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--field", default="outcome_stratum")
    parser.add_argument("--failure-values", default="tool_error")
    parser.add_argument("--window-minutes", type=float, default=30.0)
    parser.add_argument("--review-interval-days", type=int, default=90)
    parser.add_argument("--today", default=None, help="覆盖「今天」（便于确定性复现）")
    parser.add_argument("--min-domains", type=int, default=2,
                        help="来源集中度的阈值（P2-3）：唯一域名少于该数即算单一来源")
    parser.add_argument("--observation-limit", type=int, default=500,
                        help="上游对 observation 的截断上限（P3-1）；用来数「恰好达上限」的样本")
    parser.add_argument("--answer-limit", type=int, default=1000,
                        help="上游对 final_answer 的截断上限（P3-1）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    index = json.loads((args.batch / "search_steps.json").read_text(encoding="utf-8"))
    samples = index.get("samples") or []
    meta = index.get("meta") or {}
    values = tuple(v.strip() for v in str(args.failure_values).split(",") if v.strip())

    clusters = failure_clusters(
        samples, field=args.field, values=values, window_minutes=args.window_minutes
    )
    freshness = snapshot_freshness(
        args.batch, samples,
        review_interval_days=args.review_interval_days, today=args.today,
    )
    reconciliation = reconcile_outcome_strata(meta, samples)
    coverage = coverage_report_state(args.batch)
    concentration = source_concentration(samples, min_domains=args.min_domains)
    ledger = rejection_ledger_state(args.batch)
    truncation = truncation_evidence(
        samples,
        limits={"observation": args.observation_limit, "final_answer": args.answer_limit},
    )

    report = {
        "batch": str(args.batch),
        "n_samples": len(samples),
        "failure_clusters": clusters,
        "snapshot_freshness": freshness,
        "outcome_strata_reconciliation": reconciliation,
        "coverage_report": coverage,
        "source_concentration": concentration,
        "rejection_ledger": ledger,
        "truncation_evidence": truncation,
    }
    out = args.out or (args.batch / "evidence_integrity.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== 证据完整性：{args.batch.name}（{len(samples)} 个样本）")
    print(f"\n[1] 失败成簇（{clusters['field']} ∈ {list(values)}，窗口 {args.window_minutes:g} 分钟）")
    print(f"  失败样本 {clusters['n_failing_samples']} 条 → 实际来自 "
          f"**{clusters['n_requests']} 个请求**、**{clusters['n_windows']} 个时间窗**")
    print(f"  单请求最多 {clusters['max_samples_per_request']} 条；单窗口最多 "
          f"{clusters['max_samples_per_window']} 条｜来源构成 {clusters['by_provenance']}")
    for window in clusters["windows"]:
        print(f"    · {window['start']} → {window['end']}"
              f"（{window['span_minutes']} 分钟，{window['n_samples']} 条）")
    print(f"  ↳ {clusters['independent_units_note']}")

    print("\n[2] 快照寿期")
    print(f"  快照 {freshness['n_snapshots']} 份｜今天 {freshness['today']}"
          f"｜寿期来源 {freshness['policy_source_counts']}｜**已过期 {freshness['n_overdue']} 份**")
    print(f"  最早 {freshness['oldest']}｜最新 {freshness['newest']}")
    for row in freshness["overdue"]:
        print(f"    ⚠️ {row['snapshot_id']} 复核到期 {row['review_by']}"
              f"（超期 {-row['days_left']:g} 天）→ **降级引用或作废**")
    print(f"  ↳ {freshness['note']}")

    print("\n[3] meta 与样本对账")
    print(f"  meta 声明：{reconciliation['declared']}（合计 {reconciliation['declared_total']}）")
    print(f"  样本真实：{reconciliation['actual']}（合计 {reconciliation['actual_total']}"
          f" / 共 {reconciliation['n_samples']} 行）")
    if reconciliation["consistent"]:
        print("  ✅ 一致")
    else:
        print(f"  ❌ **不一致**：meta 漏掉 {reconciliation['missing_from_meta']}"
              "（同族错误：口径与真实取值不一致且静默）")

    print("\n[4] 覆盖率门禁报告")
    if coverage["present"] and coverage.get("readable"):
        print(f"  ok={coverage['ok']}｜problems={coverage['problems']}")
    else:
        print(f"  {coverage.get('note') or coverage}")

    print(f"\n[5] 来源集中度（P2-3，min_domains={concentration['min_domains']}）")
    counts = concentration["counts"]
    print(f"  请求 {concentration['n_requests']} 个 → **证据缺失 {counts['no_evidence']}**"
          f"｜单一来源 {counts['single_source']}｜多来源 {counts['multi_source']}")
    if counts["no_evidence"]:
        print(f"    · 0 域名（检索没带回任何来源）：{concentration['no_evidence'][:12]}")
    if counts["single_source"]:
        print(f"    · 单一来源（引用其「有据」须限定）：{concentration['single_source']}")
    print(f"  ↳ {concentration['note']}")

    print("\n[6] 拒绝留档（P2-1）")
    if ledger["present"] and ledger.get("readable"):
        print(f"  条目 {ledger['n_entries']} 条｜按类别 {ledger['counts_by_category']}")
        print(f"  （本阶段看不见的类别：{ledger['not_visible_here']}）")
    else:
        print(f"  {ledger.get('note') or ledger}")

    print("\n[7] 材料截断（P3-1，上限来自**上游记录器**）")
    for field, item in truncation["by_field"].items():
        print(f"  {field:14} 上限 {item['limit']:5}｜**恰好达上限 {item['at_limit_samples']} 条**"
              f"（占比 {item['at_limit_share']}）｜最长 {item['max_length']}")
    print(f"  ↳ {truncation['note']}")

    print(f"\n[written] {out}")
    print("> 本脚本**只报告、不判定门禁**，一律退出 0；门禁在采集侧（P0-2）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
