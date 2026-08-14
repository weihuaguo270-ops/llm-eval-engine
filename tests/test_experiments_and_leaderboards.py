from eval_engine.benchmark.leaderboard import analyze_leaderboards, analyze_paired_leaderboard
from eval_engine.observability.experiments import analyze_paired_experiment


def test_paired_experiment_keeps_uncertainty_and_guardrails():
    rows = [
        {"task_id": f"t{i}", "baseline": {"task_success": 0, "latency_ms": 100, "cost": 1},
         "candidate": {"task_success": 1, "latency_ms": 102, "cost": 1}}
        for i in range(5)
    ]
    report = analyze_paired_experiment(rows)
    assert report["decision"] == "pass"
    assert report["candidate_wins"] == 5


def test_leaderboard_uses_percentiles_and_pareto_not_raw_score_average():
    records = [
        {"benchmark": "image", "model_version": "a", "score": 80, "cost": 2, "latency": 100},
        {"benchmark": "image", "model_version": "b", "score": 70, "cost": 1, "latency": 50},
        {"benchmark": "video", "model_version": "a", "score": 0.6, "cost": 2, "latency": 100},
        {"benchmark": "video", "model_version": "b", "score": 0.7, "cost": 1, "latency": 50},
    ]
    report = analyze_leaderboards(records)
    assert report["benchmarks"] == ["image", "video"]
    assert "mean_percentile" in report["aggregate"][0]
    assert "b" in report["pareto_models"]


def test_paired_leaderboard_reports_uncertainty_held_out_and_latency():
    records = []
    for index in range(10):
        for model, score, latency in (("a", 0.4 + index / 100, 100), ("b", 0.3, 50)):
            records.append({"case_id": f"c{index}", "split": "held_out" if index > 6 else "golden",
                            "model": model, "model_version": f"{model}-v1", "latency_ms": latency,
                            "automatic_metrics": {"score": score}, "safety_result": {"passed": True}})
    report = analyze_paired_leaderboard(records, metric="automatic_metrics.score", bootstrap_samples=100)
    assert report["leader"] == "a"
    assert report["paired_cases"] == 10
    assert report["statistically_separated"] is True
    assert report["ranking"][0]["held_out_mean_score"] is not None
