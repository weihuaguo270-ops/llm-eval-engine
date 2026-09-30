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
    # 轨迹内多模态过程归因（非生成模型选型）
    "unnecessary_generation",
    "wrong_media_args",
    "ungrounded_vision",
    "unsafe_media",
    "other",
    "unscored",
)

_TYPE_LABELS = {
    "wrong_tool": "工具选择错误",
    "wrong_params": "参数/调用错误",
    "hallucination": "幻觉/不忠实",
    "error_propagation": "错误传播",
    "inefficient_loop": "冗余/低效循环",
    "safety_violation": "安全违规",
    "judge_error": "Judge 异常",
    "unnecessary_generation": "多余媒体生成",
    "wrong_media_args": "媒体参数错误",
    "ungrounded_vision": "视觉未接地",
    "unsafe_media": "不安全媒体",
    "other": "其他",
    "unscored": "未评估（无评分证据）",
}

_MULTIMODAL_STRUCTURED = frozenset(
    {
        "unnecessary_generation",
        "wrong_media_args",
        "ungrounded_vision",
        "unsafe_media",
        "safety_violation",
        "judge_error",
        "inefficient_loop",
    }
)


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
    if not getattr(step, "applicable", True):
        return None  # 不适用（如思考步）：不在评分范围内，不算失败
    if not step.needs_revision and step.step_score >= 3.5:
        return None

    if step.step_score <= 0:
        # 未评估：有 needs_revision 但没有分数。不得归类为下游错误传播——
        # 一个没被评过的步骤既不是根因，也不是"受影响的下游"。
        # 但 Judge 自身异常要保留 judge_error：那不是"没评"，是"评崩了"。
        reasons = " ".join(r.reason for r in step.rubrics if r.reason)
        dims = " ".join(r.dimension for r in step.rubrics)
        blob = f"{reasons} {dims} {step.role_understanding}".lower()
        judge_failed = _match_patterns(
            blob, ("judge 调用异常", "judge 异常", "judge error")
        )
        return FailureRecord(
            case_id=case_id,
            step_index=step.step_index,
            failure_type="judge_error" if judge_failed else "unscored",
            step_score=0.0,
            reason="Judge 异常" if judge_failed else "该步没有评分结果（未评估）",
            is_root_cause=False,
            tool_name=step.tool_name,
        )

    error_sources = error_sources or []

    structured = getattr(step, "failure_type", None)
    if structured and structured in FAILURE_TYPES:
        keep_structured = structured in _MULTIMODAL_STRUCTURED or any(
            (getattr(r, "check_source", "") or "")
            in ("trace_debugger", "eval_contract", "multimodal_step")
            for r in step.rubrics
        )
        if (
            step.step_index not in error_sources
            and error_sources
            and not keep_structured
        ):
            ftype = "error_propagation"
        else:
            ftype = structured
        reasons = " ".join(r.reason for r in step.rubrics if r.reason)
        primary_reason = (
            reasons.strip() or step.role_understanding or "低分未标注原因"
        )
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

    reasons = " ".join(r.reason for r in step.rubrics if r.reason)
    dims = " ".join(r.dimension for r in step.rubrics)
    blob = f"{reasons} {dims} {step.role_understanding}".lower()

    if _match_patterns(blob, ("judge 调用异常", "judge 异常", "judge error")):
        ftype = "judge_error"
    elif _match_patterns(
        blob, ("unnecessary_generation", "乱出图", "多余生成", "media_timing")
    ):
        ftype = "unnecessary_generation"
    elif _match_patterns(
        blob, ("wrong_media_args", "media_arg", "artifact_attachment", "缺少 prompt")
    ):
        ftype = "wrong_media_args"
    elif _match_patterns(
        blob, ("ungrounded_vision", "未 grounded", "未接地", "视觉幻觉")
    ):
        ftype = "ungrounded_vision"
    elif _match_patterns(blob, ("unsafe_media", "media_safety", "nsfw", "违规媒体")):
        ftype = "unsafe_media"
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
