from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle


def _episode(episode_id="e1", *, split="held_out", passed=True):
    return {
        "schema_version": "evaluation-episode/v1",
        "episode_id": episode_id,
        "split": split,
        "state_verification": {"passed": passed},
    }


def _performance(passed=True):
    return {
        "schema_version": "agent-release-evidence/v1",
        "evidence_type": "inference_performance",
        "passed": passed,
    }


def test_bundle_passes_independent_evidence():
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        process_quality={"overall_score": 4.2},
        failure_gate={"decision": "pass"},
        performance_evidence=_performance(),
    )
    assert result["decision"] == "pass"
    assert result["evidence"]["held_out_episodes"] == 1


def test_bundle_holds_business_state_failure_even_with_high_judge_score():
    result = evaluate_evidence_bundle(
        episodes=[_episode(passed=False)],
        process_quality={"overall_score": 5.0},
        failure_gate={"decision": "pass"},
        performance_evidence=_performance(),
    )
    assert result["decision"] == "hold"
    assert "business-state failures" in result["hard_failures"][0]


def test_bundle_holds_performance_budget_and_reviews_missing_held_out():
    held = evaluate_evidence_bundle(
        episodes=[_episode(split="golden")],
        performance_evidence=_performance(passed=False),
    )
    assert held["decision"] == "hold"
    assert "performance budget failed" in held["hard_failures"]

    review = evaluate_evidence_bundle(episodes=[_episode(split="golden")])
    assert review["decision"] == "review"
    assert review["review_reasons"] == ["no held_out episodes"]
