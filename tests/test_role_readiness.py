import pytest

from eval_engine.readiness import audit_role_readiness


def test_core_gap_cannot_be_averaged_away():
    evidence = {name: {"level": "production"} for name in (
        "agent_task_evaluation", "trajectory_evaluation", "judge_human_calibration",
        "safety_evaluation", "leaderboard_statistics", "online_evaluation")}
    evidence["multimodal_generation_evaluation"] = {"level": "interface"}
    report = audit_role_readiness("agent_evaluation", evidence)
    assert report["decision"] == "not_ready"
    assert report["coverage"] > 0.8
    assert report["core_gaps"] == ["multimodal_generation_evaluation"]


def test_all_evidence_is_resume_ready():
    names = ("deterministic_regression", "non_deterministic_testing", "failure_triage",
             "release_gate", "service_reliability", "production_incident_feedback")
    report = audit_role_readiness("ai_quality_engineering", {name: {"level": "offline_real"} for name in names})
    assert report["decision"] == "ready"


def test_unknown_evidence_level_is_rejected():
    with pytest.raises(ValueError, match="invalid evidence level"):
        audit_role_readiness("agent_application_engineering", {"agent_runtime": {"level": "almost_done"}})
