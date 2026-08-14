from examples.run_expense_release_pipeline import (
    _compare_versions,
    _feedback_queue,
    _human_review,
    DEFAULT_HUMAN_REVIEW,
)


def _episode(case_id, passed):
    return {
        "episode_id": case_id,
        "agent_version": "v2",
        "split": "held_out",
        "state_verification": {"passed": passed},
    }


def test_version_regression_is_promoted_to_feedback_queue():
    baseline = [_episode("case-1", True)]
    candidate = [_episode("case-1", False)]
    comparison = _compare_versions(baseline, candidate)
    review = _human_review(DEFAULT_HUMAN_REVIEW)
    feedback = _feedback_queue(
        candidate,
        comparison,
        {"trajectories": [{"session_id": "case-1", "failure_types": ["no_answer"]}]},
        review,
    )
    assert comparison["decision"] == "hold"
    assert feedback[0]["reasons"] == ["business_state_regression", "trajectory:no_answer"]
