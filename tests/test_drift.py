from eval_engine.observability.drift import (
    DriftThresholds,
    compare_batches,
    release_decision,
    summarize_batch,
)


def _baseline():
    return [
        {"category": "rag", "passed": True, "overall_score": 4.5, "latency_ms": 100, "tokens": 100},
        {"category": "rag", "passed": True, "overall_score": 4.3, "latency_ms": 120, "tokens": 110},
        {"category": "tool", "passed": True, "overall_score": 4.2, "latency_ms": 90, "tokens": 90},
        {"category": "tool", "passed": True, "overall_score": 4.1, "latency_ms": 95, "tokens": 95},
    ]


def test_batch_summary_and_stable_comparison():
    baseline = _baseline()
    summary = summarize_batch(baseline)
    assert summary["case_count"] == 4
    assert summary["pass_rate"] == 1.0
    report = compare_batches(baseline, baseline)
    assert report["drift_detected"] is False
    assert report["alerts"] == []


def test_drift_detects_quality_cost_and_slice_regressions():
    current = [
        {"category": "rag", "passed": False, "overall_score": 2.0, "latency_ms": 300, "tokens": 300},
        {"category": "rag", "passed": False, "overall_score": 2.2, "latency_ms": 320, "tokens": 310},
        {"category": "tool", "passed": True, "overall_score": 4.2, "latency_ms": 95, "tokens": 100},
        {"category": "tool", "passed": True, "overall_score": 4.1, "latency_ms": 100, "tokens": 100},
    ]
    report = compare_batches(
        _baseline(),
        current,
        thresholds=DriftThresholds(min_slice_size=2),
    )
    metrics = {alert["metric"] for alert in report["alerts"]}
    assert report["drift_detected"] is True
    assert "pass_rate" in metrics
    assert "p95_latency_ratio" in metrics
    assert "category:rag:pass_rate" in metrics


def test_release_gate_combines_independent_evidence():
    stable = compare_batches(_baseline(), _baseline())
    passed = release_decision(
        dataset_audit={"passed": True, "fingerprint": "abc"},
        drift_report=stable,
        safety_report={"attack_success_rate": 0.0},
        judge_calibration={
            "gate_split": "held_out",
            "by_split": {"held_out": {"kappa": 0.73}},
        },
    )
    assert passed["passed"] is True

    blocked = release_decision(
        dataset_audit={"passed": False},
        drift_report=stable,
        safety_report={"attack_success_rate": 0.25},
        judge_calibration={
            "gate_split": "held_out",
            "by_split": {"held_out": {"kappa": 0.4}},
        },
    )
    assert blocked["blocked"] is True
    assert set(blocked["reasons"]) == {
        "dataset_audit_failed",
        "safety_attack_success_rate_exceeded",
        "judge_calibration_below_threshold",
    }
