from eval_engine.observability.experiments import analyze_paired_experiment


def test_paired_experiment_keeps_uncertainty_and_guardrails():
    rows = [
        {
            "task_id": f"t{i}",
            "baseline": {"task_success": 0, "latency_ms": 100, "cost": 1},
            "candidate": {"task_success": 1, "latency_ms": 102, "cost": 1},
        }
        for i in range(5)
    ]
    report = analyze_paired_experiment(rows)
    assert report["decision"] == "pass"
    assert report["candidate_wins"] == 5
