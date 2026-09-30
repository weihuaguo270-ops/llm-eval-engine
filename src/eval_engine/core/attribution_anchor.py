"""attribution_anchor — 用确定性失败步校验过程归因（无需人工标注）

``report.error_sources``（根因步）由两件事合成：Judge 的语义步骤分 + DAG 拓扑
（低于阈值且上游无低分节点）。两者都可能出错。而 trace-debugger 的硬失败步是
**定义性**的：工具报错的那一步就是报错的那一步。

于是对带 trace-debugger findings 的轨迹可以做一个**必要条件**检查：
某步被确定性判为失败时，``error_sources`` 必须包含它；否则归因与确定性事实不一致
（Judge 漏评了真正失败的那一步，或拓扑把它归到了别处）。

边界（请勿过度解读）：

- 这**不是**「根因判对率」。它只查必要条件；``error_sources`` 里那些没有锚点的步骤
  是否正确，仍需人工标注（见 ``docs/SECOND_RATER_PROTOCOL.md``）。
- 只把**步骤可锚定**的类型当锚点：``no_answer`` / ``llm_offtrack`` 由分析器挂在
  最后一步，其 ``step_index`` 是汇报位置而非定位主张，故默认排除。
- 归一化复用 ``analyze_trajectory_findings``（1-based → 0-based），与 scoring 路径同源，
  避免锚点与 ``error_sources`` 差一步。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

from eval_engine.integrations.trace_findings import analyze_trajectory_findings

# 步骤可锚定：finding 的 step_index 是「这一步确实失败了」的定位主张
CORE_STEP_ANCHORED_TYPES = frozenset({
    "tool_error",
    "acceptance_failed",
    "approval_denied",
    "incomplete_stream",
    "search_empty",
    "search_weak",
    "search_timeout",
    "duplicate",
    "context_overflow",
})

# 媒体规则类型。当前 trace-debugger checkout 未产出这些 id，但 episode 内嵌的
# trace_analysis 里存在，保留以兼容；这些规则本身属于跨仓 taxonomy 待对齐项。
MEDIA_STEP_ANCHORED_TYPES = frozenset({
    "unnecessary_generation",
    "wrong_media_args",
    "ungrounded_vision",
    "unsafe_media",
})

STEP_ANCHORED_TYPES = CORE_STEP_ANCHORED_TYPES | MEDIA_STEP_ANCHORED_TYPES

# 明确不作为锚点：分析器挂在最后一步，step_index 不代表根因位置
NON_ANCHOR_TYPES = frozenset({"no_answer", "llm_offtrack"})


def anchor_steps(
    trajectory: Optional[Mapping[str, Any]] = None,
    *,
    analysis: Optional[Mapping[str, Any]] = None,
    types: Optional[Iterable[str]] = None,
) -> dict[int, list[str]]:
    """确定性失败步 -> 该步的失败类型（0-based，与 error_sources 同尺度）。

    ``analysis`` 为空时走 trace-debugger 实时分析（需已安装）；无 step_index 的
    finding（如路径级失败）无法锚定，直接忽略。
    """
    allowed = set(types) if types is not None else set(STEP_ANCHORED_TYPES)
    report = analyze_trajectory_findings(trajectory or {}, analysis=analysis)
    anchors: dict[int, list[str]] = {}
    for finding in report.findings:
        if finding.step_index is None:
            continue
        raw = finding.raw_failure_type or finding.failure_type
        if raw not in allowed:
            continue
        step = int(finding.step_index)
        bucket = anchors.setdefault(step, [])
        if raw not in bucket:
            bucket.append(raw)
    return anchors


def cross_check_attribution(
    report: Any,
    trajectory: Optional[Mapping[str, Any]] = None,
    *,
    analysis: Optional[Mapping[str, Any]] = None,
    episode_id: str = "",
    types: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """把一条轨迹的确定性锚点与其 error_sources 对齐，返回可审计的结果。"""
    anchors = anchor_steps(trajectory, analysis=analysis, types=types)
    sources = sorted({int(s) for s in (getattr(report, "error_sources", None) or [])})
    source_set = set(sources)
    agreed = sorted(step for step in anchors if step in source_set)
    missed = sorted(step for step in anchors if step not in source_set)
    return {
        "episode_id": episode_id,
        "anchors": {str(step): sorted(types_) for step, types_ in sorted(anchors.items())},
        "error_sources": sources,
        "agreed_steps": agreed,
        "missed_steps": missed,
        "unaided_sources": [step for step in sources if step not in anchors],
        "anchor_total": len(anchors),
        "anchor_hit": len(agreed),
    }


def summarize_cross_checks(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """汇总多条结果。``anchor_consistency`` 是必要条件通过率，不是根因判对率。"""
    total = sum(int(r.get("anchor_total", 0)) for r in results)
    hit = sum(int(r.get("anchor_hit", 0)) for r in results)
    with_anchor = [r for r in results if int(r.get("anchor_total", 0))]
    return {
        "n_episodes": len(results),
        "n_episodes_with_anchor": len(with_anchor),
        "anchor_total": total,
        "anchor_hit": hit,
        "anchor_miss": total - hit,
        "anchor_consistency": round(hit / total, 4) if total else None,
        "unaided_sources": sum(len(r.get("unaided_sources") or []) for r in results),
        "misses": [
            {"episode_id": r.get("episode_id", ""), "steps": list(r.get("missed_steps") or [])}
            for r in results
            if r.get("missed_steps")
        ],
        "note": "必要条件检查：确定性失败步是否被归因；不是根因判对率。",
    }


def format_cross_check(summary: Mapping[str, Any]) -> str:
    lines = ["=" * 60, "  归因锚点交叉校验（确定性失败步 vs error_sources）", "=" * 60]
    lines.append(
        f"  轨迹数: {summary.get('n_episodes')}  "
        f"含锚点轨迹: {summary.get('n_episodes_with_anchor')}"
    )
    total = summary.get("anchor_total", 0)
    if not total:
        lines.append("")
        lines.append("  ⚠ 无可用锚点：这些轨迹没有确定性失败步，或未提供 trace-debugger 分析。")
        lines.append("    本检查需要「硬失败步 + Judge 步骤分」同时存在。")
        lines.append("=" * 60)
        return "\n".join(lines)

    rate = summary.get("anchor_consistency")
    lines.append(f"  锚点总数: {total}   已被归因: {summary.get('anchor_hit')}   漏归因: {summary.get('anchor_miss')}")
    lines.append(f"  必要条件通过率: {rate:.1%}" if rate is not None else "  必要条件通过率: n/a")
    lines.append(f"  无锚点的 error_sources（正确性需人工标注）: {summary.get('unaided_sources')}")
    misses = summary.get("misses") or []
    if misses:
        lines.append("")
        lines.append(f"  漏归因明细（{len(misses)} 条轨迹，前 10）:")
        for item in misses[:10]:
            lines.append(f"    {item['episode_id']}: step {item['steps']}")
    lines.append("")
    lines.append("  口径：这是必要条件检查，不是根因判对率。")
    lines.append("=" * 60)
    return "\n".join(lines)
