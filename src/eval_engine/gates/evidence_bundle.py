"""Release decision over independent business, quality, failure, and performance evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from eval_engine.core.verdict import MIN_JUDGED_FOR_RATE

#: 判定结果证据的 schema 版本（与其它证据块同一约定：不匹配即 hold）
VERDICT_EVIDENCE_SCHEMA = "verdict-evidence/v1"


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
    verdict_evidence: Mapping[str, Any] | None = None,
    verdict_policy: Mapping[str, Any] | None = None,
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

    ``verdict_evidence`` (``verdict-evidence/v1``) is the **decision-level result**
    (缺陷率 / 漏杀 per block, produced by ``examples/run_result_evaluation.py``) and
    ``verdict_policy`` is the **threshold the release owner declares**. 证据与政策分开：
    **没有政策就不许判过**（``review``）——"数字在、但没人说多少算不合格"不是通过的理由。
    阈值**不设默认值**：本模块不替发布方拍一个数。
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

    # **判定结果**（决策级）进门禁：这就是"发布门禁消费判定结果"那一步。
    # 它与下面的 P3 身份检查**共用同一套规则**——`verdict_evidence` 自带的 `bands_identity`
    # 会被喂给下面那段，**不另立一套口径**。
    verdict_evidence_summary: dict[str, Any] | None = None
    if verdict_evidence is not None:
        if verdict_evidence.get("schema_version") != VERDICT_EVIDENCE_SCHEMA:
            reasons.append("unsupported verdict evidence schema")
        else:
            if verdict_criteria is None:
                carried = dict(verdict_evidence.get("bands_identity") or {})
                if verdict_evidence.get("expected_bands_sha256"):
                    carried["expected_sha256"] = verdict_evidence["expected_bands_sha256"]
                # **证据在场却指不出判据** ⇒ 不得判过。否则"没配身份"会在这条新路径上
                # 静默放行——那正是 P3 那个病的同构体（能力在、却没人查）。
                # 带 `recognized is False` 的身份**不算"空手来"**：它会被下面那段报出来。
                if not carried.get("sha256") and carried.get("recognized") is not False:
                    review_reasons.append(
                        "verdict evidence carries no recognizable bands identity"
                    )
                verdict_criteria = carried or None
            blocks = [
                b for b in (verdict_evidence.get("blocks") or []) if isinstance(b, Mapping)
            ]
            verdict_evidence_summary = {
                "blocks": len(blocks),
                "policy": dict(verdict_policy) if verdict_policy else None,
                "insufficient": [],
                "above_policy": [],
            }
            if not verdict_policy or verdict_policy.get("max_judge_defect_rate") is None:
                # 有数字、没政策 ⇒ 不得判过（**本模块不替发布方拍一个阈值**）
                review_reasons.append("verdict evidence has no declared policy")
            else:
                threshold = float(verdict_policy["max_judge_defect_rate"])
                max_false_pass = verdict_policy.get("max_false_pass")
                usable = 0
                for block in blocks:
                    label = str(block.get("label") or "unknown")
                    n = int(block.get("n") or 0)
                    if n < MIN_JUDGED_FOR_RATE:
                        # 样本不足 ⇒ **不支持率结论**：不参与判定，但**必须显式列出**
                        # （否则"没算"又会被读成"没缺陷"）
                        verdict_evidence_summary["insufficient"].append({"label": label, "n": n})
                        continue
                    usable += 1
                    rate = float(block.get("judge_defect_rate") or 0.0)
                    ci = (
                        block.get("defect_rate_ci_cluster")
                        or block.get("defect_rate_ci_item")
                        or []
                    )
                    low = float(ci[0]) if ci else None
                    if rate > threshold:
                        verdict_evidence_summary["above_policy"].append(
                            {"label": label, "judge_defect_rate": rate, "ci_low": low}
                        )
                        if low is not None and low > threshold:
                            # 区间下界都超阈 ⇒ **稳健超标**，不是噪声
                            reasons.append(
                                f"verdict defect rate above policy in {label}: {rate:.3f} "
                                f"(95% CI lower {low:.3f} > {threshold:.3f})"
                            )
                        else:
                            # 点估计超阈但区间跨阈 ⇒ 需人看，不直接判死
                            review_reasons.append(
                                f"verdict defect rate above policy in {label}: {rate:.3f} "
                                f"(CI straddles {threshold:.3f})"
                            )
                    if max_false_pass is not None and int(block.get("false_pass") or 0) > int(
                        max_false_pass
                    ):
                        reasons.append(
                            f"verdict false-pass above policy in {label}: "
                            f"{int(block.get('false_pass') or 0)} > {int(max_false_pass)}"
                        )
                if blocks and not usable:
                    review_reasons.append(
                        "no verdict block has enough judged cells to support a rate"
                    )

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
            "verdict_evidence_present": verdict_evidence is not None,
            "verdict_policy_declared": bool(verdict_policy),
            "verdict_evidence": verdict_evidence_summary,
        },
    }
