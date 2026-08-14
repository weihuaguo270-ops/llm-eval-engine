"""Audit portfolio evidence against broad enterprise role responsibilities."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Mapping


class EvidenceLevel(IntEnum):
    missing = 0
    interface = 1
    fixture = 2
    offline_real = 3
    production = 4


_ROLE_CATALOG = {
    "agent_application_engineering": ("Agent 应用研发", {
        "agent_runtime": 1, "rag_and_tools": 1, "external_system_integration": 1,
        "business_task_success": 1, "deployment_service": 1,
        "online_observability": 0, "feedback_iteration": 0,
    }),
    "llm_application_engineering": ("大模型应用研发", {
        "model_provider_integration": 1, "rag_and_context_engineering": 1,
        "business_task_success": 1, "quality_cost_latency_tradeoff": 1,
        "online_experiment": 1, "feedback_iteration": 0,
    }),
    "agent_evaluation": ("Agent 评测", {
        "agent_task_evaluation": 1, "trajectory_evaluation": 1,
        "judge_human_calibration": 1, "multimodal_generation_evaluation": 1,
        "safety_evaluation": 1, "leaderboard_statistics": 1, "online_evaluation": 0,
    }),
    "ai_quality_engineering": ("AI 应用测试/质量工程", {
        "deterministic_regression": 1, "non_deterministic_testing": 1,
        "failure_triage": 1, "release_gate": 1, "service_reliability": 1,
        "production_incident_feedback": 0,
    }),
}


def role_catalog() -> dict[str, dict[str, Any]]:
    return {
        role: {"title": title, "requirements": {name: {"core": bool(core), "minimum": "offline_real"}
            for name, core in requirements.items()}}
        for role, (title, requirements) in _ROLE_CATALOG.items()
    }


def audit_role_readiness(role: str, evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Require real evidence for every core responsibility; do not average gaps away."""
    if role not in _ROLE_CATALOG:
        raise KeyError(f"unknown role: {role}")
    title, requirements = _ROLE_CATALOG[role]
    rows, core_gaps, supporting_gaps = [], [], []
    for capability, core in requirements.items():
        item = evidence.get(capability) or {}
        raw_level = str(item.get("level") or "missing")
        try:
            actual = EvidenceLevel[raw_level]
        except KeyError as exc:
            raise ValueError(f"invalid evidence level for {capability}: {raw_level}") from exc
        passed = actual >= EvidenceLevel.offline_real
        rows.append({"capability": capability, "core": bool(core), "required_level": "offline_real",
                     "actual_level": actual.name, "passed": passed,
                     "artifacts": list(item.get("artifacts") or []),
                     "gap": str(item.get("gap") or "") if not passed else ""})
        if not passed:
            (core_gaps if core else supporting_gaps).append(capability)
    coverage = sum(row["passed"] for row in rows) / len(rows) if rows else 0.0
    decision = "not_ready" if core_gaps else "conditional" if supporting_gaps else "ready"
    return {"role": role, "title": title, "decision": decision, "resume_ready": decision == "ready",
            "coverage": round(coverage, 4), "core_gaps": core_gaps, "supporting_gaps": supporting_gaps,
            "requirements": rows,
            "rule": "Core capabilities require offline_real or production evidence; strengths do not offset gaps."}
