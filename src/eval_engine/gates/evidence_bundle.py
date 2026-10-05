"""Release decision over independent business, quality, failure, and performance evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def evaluate_evidence_bundle(
    *,
    episodes: Sequence[Mapping[str, Any]],
    process_quality: Mapping[str, Any] | None = None,
    failure_gate: Mapping[str, Any] | None = None,
    performance_evidence: Mapping[str, Any] | None = None,
    dataset_audit: Mapping[str, Any] | None = None,
    version_comparison: Mapping[str, Any] | None = None,
    human_review: Mapping[str, Any] | None = None,
    multimodal_understanding: Mapping[str, Any] | None = None,
    verdict_criteria: Mapping[str, Any] | None = None,
    min_process_score: float = 3.5,
) -> dict[str, Any]:
    """Fail closed on business state and budgets; keep Judge quality separate.

    Every evidence block is **presence-conditional**: ``None`` means "not evaluated on
    this path" and is recorded as ``*_present: False`` — never guessed into a verdict.
    ``verdict_criteria`` carries the decision criteria's own identity (合格线 identity,
    see `docs/VERDICT_IDENTITY_PLAN.md`) and applies the **two-level** check:
    unrecognized / mismatched-against-expectation ⇒ ``review``; a *declared* identity
    contradicting the *recomputed* one ⇒ ``hold`` (the artifact contradicts itself —
    that is the fail-closed case, not a configuration problem).
    """
    reasons: list[str] = []
    review_reasons: list[str] = []

    if dataset_audit is not None and dataset_audit.get("passed") is not True:
        reasons.append("dataset audit failed")
    if version_comparison is not None:
        if version_comparison.get("decision") == "hold":
            reasons.append("business version comparison=hold")
        elif version_comparison.get("decision") == "review":
            review_reasons.append("business version comparison=review")

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
        # None 表示「没有任何步骤被评分」，不能强转成 0.0 —— 那会把"未评分"读成"最差"。
        raw_score = process_quality.get("overall_score")
        if raw_score is None:
            review_reasons.append("process score missing (no scored steps)")
        else:
            score = float(raw_score)
            if score < min_process_score:
                review_reasons.append(
                    f"process score {score:.3f} below {min_process_score:.3f}"
                )

    if human_review is not None:
        reviewed = int(human_review.get("reviewed_cases") or 0)
        required = int(human_review.get("required_cases") or 0)
        rejected = list(human_review.get("rejected_case_ids") or [])
        if reviewed < required:
            review_reasons.append(
                f"human review coverage {reviewed}/{required} below requirement"
            )
        if rejected:
            reasons.append(f"human review rejected cases: {rejected}")

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

    if multimodal_understanding is not None:
        if multimodal_understanding.get("schema_version") != "multimodal-understanding-evidence/v1":
            reasons.append("unsupported multimodal understanding evidence schema")
        else:
            for item in multimodal_understanding.get("hard_failures") or []:
                reasons.append(f"multimodal understanding: {item}")
            decision_value = str(
                multimodal_understanding.get("gate_decision")
                or ("pass" if multimodal_understanding.get("passed") is True else "")
            )
            if decision_value == "hold" and not multimodal_understanding.get("hard_failures"):
                reasons.append("multimodal understanding gate=hold")
            elif decision_value == "review":
                for item in multimodal_understanding.get("review_reasons") or [
                    "multimodal understanding gate=review"
                ]:
                    review_reasons.append(f"multimodal understanding: {item}")
            elif (
                multimodal_understanding.get("passed") is not True
                and decision_value not in {"hold", "review", "pass"}
            ):
                reasons.append("multimodal understanding evidence failed")

    # 【P3】判定标准（合格线）身份：**两级阻断**。
    # 依据 `docs/VERDICT_IDENTITY_PLAN.md` §1 的 P3/P4：
    # 「读不到 ≠ 通过」——不可识别、或与**预期**不一致 ⇒ review（配置问题，可修）；
    # 「产物不得自相矛盾」——**声明**的身份与**重算**的身份不符 ⇒ hold（篡改/换版）。
    # 与其它证据块一样**存在即校验**：`None` 只记"没在这一步评估"，绝不代猜。
    bands_identity_evidence: dict[str, Any] | None = None
    if verdict_criteria is not None:
        actual = str(verdict_criteria.get("sha256") or "")
        expected = verdict_criteria.get("expected_sha256")
        declared = verdict_criteria.get("declared_sha256")
        bands_identity_evidence = {
            "algo": verdict_criteria.get("algo"),
            "sha256": actual or None,
            "recognized": verdict_criteria.get("recognized") is True,
            "reason": verdict_criteria.get("reason"),
            "expected_sha256": expected,
            "declared_sha256": declared,
        }
        if verdict_criteria.get("recognized") is not True:
            review_reasons.append(
                "bands identity unrecognized "
                f"({verdict_criteria.get('reason') or 'unknown'})"
            )
        else:
            if expected and not actual.startswith(str(expected)):
                review_reasons.append(
                    f"bands identity mismatch: expected {expected}, got {actual[:16]}"
                )
            if declared and str(declared) != actual:
                reasons.append(
                    "bands identity contradicts declared value: "
                    f"declared {str(declared)[:16]}, recomputed {actual[:16]}"
                )

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
            "dataset_audit_present": dataset_audit is not None,
            "version_comparison_present": version_comparison is not None,
            "human_review_present": human_review is not None,
            "multimodal_understanding_present": multimodal_understanding is not None,
            "verdict_criteria_present": verdict_criteria is not None,
            "bands_identity": bands_identity_evidence,
        },
    }
