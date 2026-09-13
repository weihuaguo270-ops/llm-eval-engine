"""trace_findings — 消费 trace-debugger 规则失败作为单一真相源

本仓不重复实现循环/盲打/工具错误等启发式扫描。
规则失败识别以 trace-debugger 为准；此处只做：
  1. 调用或接收 analysis
  2. 归一化为 check_findings
  3. 映射到本仓 failure_taxonomy 枚举
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence

# trace-debugger FailureType 字符串 → 本仓 FAILURE_TYPES
_TRACE_TO_TAXONOMY: dict[str, str] = {
    "tool_error": "wrong_params",
    "acceptance_failed": "wrong_params",
    "search_empty": "wrong_tool",
    "search_timeout": "other",
    "llm_offtrack": "hallucination",
    "context_overflow": "other",
    "duplicate": "inefficient_loop",
    "no_answer": "other",
    "unknown": "other",
}


@dataclass
class CheckFinding:
    """归一化后的单条检查发现（可供 Process Reward / taxonomy / 门禁消费）。"""

    code: str
    failure_type: str
    message: str
    step_index: Optional[int] = None
    severity: str = "fail"  # fail | warn
    score: float = 1.0
    source: str = "trace_debugger"
    tool_name: Optional[str] = None
    raw_failure_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceFindingsReport:
    """一条轨迹上的规则失败摘要。"""

    session_id: str = ""
    needs_fix: bool = False
    findings: list[CheckFinding] = field(default_factory=list)
    failure_types: list[str] = field(default_factory=list)
    fix_suggestions: list[str] = field(default_factory=list)
    analysis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "needs_fix": self.needs_fix,
            "findings": [f.to_dict() for f in self.findings],
            "failure_types": list(self.failure_types),
            "fix_suggestions": list(self.fix_suggestions),
            "source": "trace_debugger",
        }


def map_trace_failure_type(raw: str) -> str:
    """将 trace-debugger 失败类型映射到本仓 taxonomy。"""
    key = (raw or "").strip().lower()
    return _TRACE_TO_TAXONOMY.get(key, "other")


def _format_b_step_to_zero_based(step_index: int) -> int:
    """Format B 分析里的 step_index 为 1-based；本仓 DAG 为 0-based。"""
    if step_index <= 0:
        return step_index
    return step_index - 1


def normalize_analysis_dict(
    analysis: Mapping[str, Any],
    *,
    zero_based_steps: bool = True,
) -> TraceFindingsReport:
    """把 analysis_to_dict 输出归一化为 TraceFindingsReport。"""
    findings: list[CheckFinding] = []
    failure_types: set[str] = set()

    for path in analysis.get("paths") or []:
        for raw_ft in path.get("failures") or []:
            if raw_ft:
                failure_types.add(str(raw_ft))
        for step in path.get("steps") or []:
            raw_ft = str(step.get("failure_type") or "").strip()
            if not raw_ft:
                continue
            raw_idx = step.get("step_index")
            step_index: Optional[int]
            if raw_idx is None:
                step_index = None
            else:
                idx = int(raw_idx)
                step_index = (
                    _format_b_step_to_zero_based(idx) if zero_based_steps else idx
                )
            tool_name = step.get("action") or None
            if tool_name == "":
                tool_name = None
            detail = str(
                step.get("failure_detail") or step.get("suggestion") or raw_ft
            )
            findings.append(
                CheckFinding(
                    code=f"trace:{raw_ft}",
                    failure_type=map_trace_failure_type(raw_ft),
                    message=detail,
                    step_index=step_index,
                    severity="fail",
                    score=1.0,
                    source="trace_debugger",
                    tool_name=str(tool_name) if tool_name else None,
                    raw_failure_type=raw_ft,
                )
            )
            failure_types.add(raw_ft)

    return TraceFindingsReport(
        session_id=str(analysis.get("session_id") or ""),
        needs_fix=bool(analysis.get("needs_fix")),
        findings=findings,
        failure_types=sorted(failure_types),
        fix_suggestions=list(analysis.get("fix_suggestions") or []),
        analysis=dict(analysis),
    )


def analyze_trajectory_findings(
    trajectory: Mapping[str, Any],
    *,
    zero_based_steps: bool = True,
    analysis: Mapping[str, Any] | None = None,
) -> TraceFindingsReport:
    """从 Format B 轨迹得到规则失败 findings。

    优先使用调用方传入的 analysis（便于离线/测试）；
    否则调用 trace-debugger（必须已安装）。
    """
    if analysis is not None:
        return normalize_analysis_dict(analysis, zero_based_steps=zero_based_steps)

    try:
        from trace_debugger import analyze_trajectory_dict, analysis_to_dict
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "trace-debugger is required for rule-failure findings; "
            "pip install the sibling package or pass analysis=..."
        ) from exc

    payload = analysis_to_dict(analyze_trajectory_dict(dict(trajectory)))
    return normalize_analysis_dict(payload, zero_based_steps=zero_based_steps)


def snapshot_episode_failures(
    episodes: Sequence[Mapping[str, Any]],
    *,
    trajectory_key: str = "trajectory",
    episode_id_key: str = "episode_id",
) -> dict[str, Any]:
    """批量轨迹失败快照（供发布流水线 / 回归门禁）。"""
    rows: list[dict[str, Any]] = []
    distribution: dict[str, int] = {}
    for episode in episodes:
        traj = episode.get(trajectory_key) or {}
        report = analyze_trajectory_findings(traj)
        for ft in report.failure_types:
            distribution[ft] = distribution.get(ft, 0) + 1
        rows.append(
            {
                "session_id": str(episode.get(episode_id_key) or report.session_id),
                "failure_types": list(report.failure_types),
                "needs_fix": report.needs_fix,
                "findings": [f.to_dict() for f in report.findings],
            }
        )
    return {
        "n_trajectories": len(rows),
        "distribution": dict(sorted(distribution.items())),
        "trajectories": rows,
        "source": "trace_debugger",
    }


def findings_by_step(
    findings: Sequence[CheckFinding],
) -> dict[int, list[CheckFinding]]:
    grouped: dict[int, list[CheckFinding]] = {}
    for item in findings:
        if item.step_index is None:
            continue
        grouped.setdefault(item.step_index, []).append(item)
    return grouped
