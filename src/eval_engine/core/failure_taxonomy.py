"""failure_taxonomy — 低分步骤失败类型归类与分布统计"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from eval_engine.core.process_reward import ProcessRewardReport, StepScore

# 标准失败类型（评测岗常用归因维度）
FAILURE_TYPES = (
    "wrong_tool",
    "wrong_params",
    "hallucination",
    "error_propagation",
    "inefficient_loop",
    "safety_violation",
    "judge_error",
    "other",
)

_TYPE_LABELS = {
    "wrong_tool": "工具选择错误",
    "wrong_params": "参数/调用错误",
    "hallucination": "幻觉/不忠实",
    "error_propagation": "错误传播",
    "inefficient_loop": "冗余/低效循环",
    "safety_violation": "安全违规",
    "judge_error": "Judge 异常",
    "other": "其他",
}


@dataclass
class FailureRecord:
    """One normalized failure assigned to the earliest causal step available."""

    case_id: str
    step_index: int
    failure_type: str
    step_score: float
    reason: str
    is_root_cause: bool = False
    tool_name: Optional[str] = None


@dataclass
class TaxonomySummary:
    """Failure counts and records emitted for one benchmark run."""

    total_failures: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    records: list[FailureRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the stable failure-taxonomy report representation."""
        return {
            "total_failures": self.total_failures,
            "by_type": self.by_type,
            "by_type_pct": {
                k: round(v / self.total_failures, 4) if self.total_failures else 0.0
                for k, v in self.by_type.items()
            },
            "by_category": self.by_category,
            "records": [
                {
                    "case_id": r.case_id,
                    "step_index": r.step_index,
                    "failure_type": r.failure_type,
                    "failure_label": _TYPE_LABELS.get(r.failure_type, r.failure_type),
                    "step_score": r.step_score,
                    "reason": r.reason,
                    "is_root_cause": r.is_root_cause,
                    "tool_name": r.tool_name,
                }
                for r in self.records
            ],
        }


def _match_patterns(text: str, patterns: list[str]) -> bool:
    t = text.lower()
    return any(p in t for p in patterns)


def classify_step_failure(
    step: StepScore,
    *,
    error_sources: Optional[list[int]] = None,
    case_id: str = "",
) -> Optional[FailureRecord]:
    """对单步低分结果归类；非低分步返回 None。"""
    if not step.needs_revision and step.step_score >= 3.5:
        return None

    error_sources = error_sources or []
    reasons = " ".join(r.reason for r in step.rubrics if r.reason)
    dims = " ".join(r.dimension for r in step.rubrics)
    blob = f"{reasons} {dims} {step.role_understanding}".lower()

    if _match_patterns(blob, ("judge 调用异常", "judge 异常", "judge error")):
        ftype = "judge_error"
    elif step.step_index in error_sources and step.step_index not in (
        s for s in error_sources if s != step.step_index
    ):
        # 根因步优先看直接错误类型；下游步单独标 propagation
        if _match_patterns(blob, ("幻觉", "hallucin", "夸大", "未支持", "矛盾", "faithfulness")):
            ftype = "hallucination"
        elif _match_patterns(blob, ("参数", "argument", "param", "调用失败", "编造")):
            ftype = "wrong_params"
        elif _match_patterns(blob, ("工具", "tool", "web_search", "calculator", "fetch")):
            ftype = "wrong_tool"
        elif _match_patterns(blob, ("安全", "safety", "rm -rf", "passwd", "删除", "execute")):
            ftype = "safety_violation"
        elif _match_patterns(blob, ("重复", "冗余", "无效", "循环", "两次")):
            ftype = "inefficient_loop"
        else:
            ftype = "other"
    elif step.step_index not in error_sources and error_sources:
        ftype = "error_propagation"
    elif _match_patterns(blob, ("幻觉", "hallucin", "faithfulness", "未支持", "夸大")):
        ftype = "hallucination"
    elif _match_patterns(blob, ("参数", "argument", "param")):
        ftype = "wrong_params"
    elif _match_patterns(blob, ("工具", "tool_selection")):
        ftype = "wrong_tool"
    elif _match_patterns(blob, ("安全", "safety", "trajectory_safety")):
        ftype = "safety_violation"
    elif _match_patterns(blob, ("重复", "冗余", "循环")):
        ftype = "inefficient_loop"
    else:
        ftype = "other"

    primary_reason = reasons.strip() or step.role_understanding or "低分未标注原因"
    primary_reason = re.sub(r"\s+", " ", primary_reason)[:200]

    return FailureRecord(
        case_id=case_id,
        step_index=step.step_index,
        failure_type=ftype,
        step_score=step.step_score,
        reason=primary_reason,
        is_root_cause=step.step_index in error_sources,
        tool_name=step.tool_name,
    )


def summarize_failures(
    reports: list[tuple[str, str, ProcessRewardReport]],
) -> TaxonomySummary:
    """汇总多条 case 的失败分布。

    reports: [(case_id, category, ProcessRewardReport), ...]
    """
    summary = TaxonomySummary()
    type_counter: Counter[str] = Counter()
    cat_type: dict[str, Counter[str]] = {}

    for case_id, category, report in reports:
        if category not in cat_type:
            cat_type[category] = Counter()
        for step in report.per_step:
            rec = classify_step_failure(
                step,
                error_sources=report.error_sources,
                case_id=case_id,
            )
            if rec is None:
                continue
            summary.records.append(rec)
            type_counter[rec.failure_type] += 1
            cat_type[category][rec.failure_type] += 1

    summary.total_failures = len(summary.records)
    summary.by_type = dict(type_counter)
    summary.by_category = {cat: dict(cnt) for cat, cnt in cat_type.items()}
    return summary
