"""Release decision over independent business, quality, failure, and performance evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def evaluate_evidence_bundle(
    *,
    episodes: Sequence[Mapping[str, Any]],
    process_quality: Mapping[str, Any] | None = None,
    failure_gate: Mapping[str, Any] | None = None,
    performance_evidence: Mapping[str, Any] | None = None,
    min_process_score: float = 3.5,
) -> dict[str, Any]:
    """Fail closed on business state and budgets; keep Judge quality separate."""
    reasons: list[str] = []
    review_reasons: list[str] = []

    if not episodes:
        reasons.append("no evaluation episodes")
    failed_business = []
    missing_business = []
    held_out = 0
    for episode in episodes:
        episode_id = str(episode.get("episode_id") or "unknown")
        if episode.get("split") == "held_out":
            held_out += 1
        verification = episode.get("state_verification")
        if not isinstance(verification, Mapping):
            missing_business.append(episode_id)
        elif verification.get("passed") is not True:
            failed_business.append(episode_id)
    if missing_business:
        reasons.append(f"missing business-state verification: {missing_business}")
    if failed_business:
        reasons.append(f"business-state failures: {failed_business}")
    if held_out == 0:
        review_reasons.append("no held_out episodes")

    if process_quality is not None:
        score = float(process_quality.get("overall_score") or 0.0)
        if score < min_process_score:
            review_reasons.append(
                f"process score {score:.3f} below {min_process_score:.3f}"
            )

    if failure_gate is not None:
        decision = str(
            failure_gate.get("decision") or failure_gate.get("gate_decision") or ""
        )
        if decision == "hold":
            reasons.append("failure regression gate=hold")
        elif decision == "review":
            review_reasons.append("failure regression gate=review")

    if performance_evidence is not None:
        if performance_evidence.get("schema_version") != "agent-release-evidence/v1":
            reasons.append("unsupported performance evidence schema")
        elif performance_evidence.get("passed") is not True:
            reasons.append("performance budget failed")

    decision = "hold" if reasons else "review" if review_reasons else "pass"
    return {
        "decision": decision,
        "passed": decision == "pass",
        "hard_failures": reasons,
        "review_reasons": review_reasons,
        "evidence": {
            "episodes": len(episodes),
            "held_out_episodes": held_out,
            "business_state_verified": len(episodes) - len(missing_business),
            "process_quality_present": process_quality is not None,
            "failure_gate_present": failure_gate is not None,
            "performance_present": performance_evidence is not None,
        },
    }
