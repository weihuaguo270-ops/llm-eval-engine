"""drift — 评测批次漂移与发布检查。"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DriftThresholds:
    """漂移门限。"""

    max_score_drop: float = 0.10
    max_pass_rate_drop: float = 0.05
    max_latency_ratio: float = 1.25
    max_token_ratio: float = 1.25
    min_slice_size: int = 2


def summarize_batch(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """汇总整体和业务切片指标。"""
    if not records:
        return {
            "case_count": 0,
            "pass_rate": 0.0,
            "avg_score": 0.0,
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "avg_tokens": 0.0,
            "by_category": {},
        }

    scores = [float(record.get("overall_score", 0.0)) for record in records]
    latencies = [float(record.get("latency_ms", 0.0)) for record in records]
    tokens = [float(record.get("tokens", 0.0)) for record in records]
    passed = [bool(record.get("passed", False)) for record in records]
    categories: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        category = str(record.get("category", "unknown"))
        categories.setdefault(category, []).append(record)

    return {
        "case_count": len(records),
        "pass_rate": round(sum(passed) / len(records), 4),
        "avg_score": round(sum(scores) / len(scores), 4),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
        "avg_tokens": round(sum(tokens) / len(tokens), 2),
        "by_category": {
            category: {
                "case_count": len(group),
                "pass_rate": round(
                    sum(bool(item.get("passed", False)) for item in group) / len(group),
                    4,
                ),
                "avg_score": round(
                    sum(float(item.get("overall_score", 0.0)) for item in group)
                    / len(group),
                    4,
                ),
            }
            for category, group in sorted(categories.items())
        },
    }


def compare_batches(
    baseline_records: Sequence[Mapping[str, Any]],
    current_records: Sequence[Mapping[str, Any]],
    *,
    thresholds: DriftThresholds | None = None,
) -> dict[str, Any]:
    """对比基线与当前批次。"""
    limits = thresholds or DriftThresholds()
    baseline = summarize_batch(baseline_records)
    current = summarize_batch(current_records)
    if not baseline["case_count"]:
        raise ValueError("baseline batch must not be empty")
    if not current["case_count"]:
        raise ValueError("current batch must not be empty")

    alerts: list[dict[str, Any]] = []
    score_delta = current["avg_score"] - baseline["avg_score"]
    pass_rate_delta = current["pass_rate"] - baseline["pass_rate"]
    latency_ratio = _safe_ratio(
        current["p95_latency_ms"], baseline["p95_latency_ms"]
    )
    token_ratio = _safe_ratio(current["avg_tokens"], baseline["avg_tokens"])

    # 整体检查覆盖质量、尾延迟和 Token 成本。
    if score_delta < -limits.max_score_drop:
        alerts.append(
            _alert("avg_score", score_delta, -limits.max_score_drop, "decrease")
        )
    if pass_rate_delta < -limits.max_pass_rate_drop:
        alerts.append(
            _alert(
                "pass_rate",
                pass_rate_delta,
                -limits.max_pass_rate_drop,
                "decrease",
            )
        )
    if latency_ratio > limits.max_latency_ratio:
        alerts.append(
            _alert(
                "p95_latency_ratio",
                latency_ratio,
                limits.max_latency_ratio,
                "increase",
            )
        )
    if token_ratio > limits.max_token_ratio:
        alerts.append(
            _alert("avg_token_ratio", token_ratio, limits.max_token_ratio, "increase")
        )

    # 总体均值会掩盖局部退化，因此单独检查样本量达标的业务切片。
    slice_deltas: dict[str, Any] = {}
    common_categories = sorted(
        set(baseline["by_category"]).intersection(current["by_category"])
    )
    for category in common_categories:
        old = baseline["by_category"][category]
        new = current["by_category"][category]
        if min(old["case_count"], new["case_count"]) < limits.min_slice_size:
            continue
        category_pass_delta = new["pass_rate"] - old["pass_rate"]
        category_score_delta = new["avg_score"] - old["avg_score"]
        slice_deltas[category] = {
            "pass_rate_delta": round(category_pass_delta, 4),
            "score_delta": round(category_score_delta, 4),
        }
        if category_pass_delta < -limits.max_pass_rate_drop:
            alerts.append(
                _alert(
                    f"category:{category}:pass_rate",
                    category_pass_delta,
                    -limits.max_pass_rate_drop,
                    "decrease",
                )
            )

    return {
        "drift_detected": bool(alerts),
        "baseline": baseline,
        "current": current,
        "deltas": {
            "avg_score": round(score_delta, 4),
            "pass_rate": round(pass_rate_delta, 4),
            "p95_latency_ratio": round(latency_ratio, 4),
            "avg_token_ratio": round(token_ratio, 4),
            "by_category": slice_deltas,
        },
        "thresholds": asdict(limits),
        "alerts": alerts,
    }


def release_decision(
    *,
    dataset_audit: Mapping[str, Any],
    drift_report: Mapping[str, Any],
    safety_report: Mapping[str, Any] | None = None,
    judge_calibration: Mapping[str, Any] | None = None,
    min_judge_kappa: float = 0.60,
    max_attack_success_rate: float = 0.0,
) -> dict[str, Any]:
    """生成发布门禁结论。"""
    # 数据、安全和 Judge 属于硬门禁，不用综合分相互抵消。
    reasons: list[str] = []
    if not dataset_audit.get("passed", False):
        reasons.append("dataset_audit_failed")
    if drift_report.get("drift_detected", False):
        reasons.append("quality_or_cost_drift")

    if safety_report is not None:
        attack_rate = safety_report.get("attack_success_rate")
        if attack_rate is not None and float(attack_rate) > max_attack_success_rate:
            reasons.append("safety_attack_success_rate_exceeded")

    if judge_calibration is not None:
        gate_split = judge_calibration.get("gate_split")
        split_metrics = (judge_calibration.get("by_split") or {}).get(gate_split, {})
        kappa = split_metrics.get("kappa", judge_calibration.get("kappa"))
        if kappa is None or float(kappa) < min_judge_kappa:
            reasons.append("judge_calibration_below_threshold")

    return {
        "passed": not reasons,
        "blocked": bool(reasons),
        "reasons": reasons,
        "evidence": {
            "dataset_fingerprint": dataset_audit.get("fingerprint"),
            "drift_alert_count": len(drift_report.get("alerts", [])),
            "attack_success_rate": (
                safety_report.get("attack_success_rate")
                if safety_report is not None else None
            ),
            "judge_gate_split": (
                judge_calibration.get("gate_split")
                if judge_calibration is not None else None
            ),
        },
    }


def _alert(
    metric: str,
    observed: float,
    threshold: float,
    direction: str,
) -> dict[str, Any]:
    return {
        "metric": metric,
        "observed": round(observed, 4),
        "threshold": round(threshold, 4),
        "direction": direction,
    }


def _safe_ratio(current: float, baseline: float) -> float:
    """处理零基线的比率计算。"""
    if baseline == 0:
        return 1.0 if current == 0 else math.inf
    return current / baseline


def _percentile(values: Sequence[float], quantile: float) -> float:
    """线性插值分位数。"""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
