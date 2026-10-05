import json

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


def test_bundle_enforces_dataset_version_and_human_review_evidence():
    held = evaluate_evidence_bundle(
        episodes=[_episode()],
        dataset_audit={"passed": False},
        version_comparison={"decision": "hold"},
        human_review={
            "reviewed_cases": 1,
            "required_cases": 2,
            "rejected_case_ids": ["e1"],
        },
    )
    assert held["decision"] == "hold"
    assert "dataset audit failed" in held["hard_failures"]
    assert "business version comparison=hold" in held["hard_failures"]
    assert "human review rejected cases" in held["hard_failures"][-1]


def test_bundle_accepts_multimodal_understanding_evidence():
    passed = evaluate_evidence_bundle(
        episodes=[_episode()],
        multimodal_understanding={
            "schema_version": "multimodal-understanding-evidence/v1",
            "gate_decision": "pass",
            "passed": True,
            "hard_failures": [],
        },
    )
    assert passed["decision"] == "pass"
    assert passed["evidence"]["multimodal_understanding_present"] is True

    held = evaluate_evidence_bundle(
        episodes=[_episode()],
        multimodal_understanding={
            "schema_version": "multimodal-understanding-evidence/v1",
            "gate_decision": "hold",
            "passed": False,
            "hard_failures": ["understanding track gate did not reach offline_real"],
        },
    )
    assert held["decision"] == "hold"
    assert "multimodal understanding: understanding track gate" in held["hard_failures"][0]


def test_bundle_treats_missing_process_score_as_unscored_not_zero():
    """未评分（overall_score=None）不得被读成 0.0 低分；真实的 0 分仍按低分处理。"""
    missing = evaluate_evidence_bundle(
        episodes=[_episode()],
        process_quality={
            "metric": "process_reward_media_steps_min",
            "overall_score": None,
        },
    )
    assert missing["decision"] == "review"
    assert any("missing" in reason for reason in missing["review_reasons"])
    assert not any("0.000" in reason for reason in missing["review_reasons"])

    zero = evaluate_evidence_bundle(
        episodes=[_episode()],
        process_quality={"overall_score": 0.0},
    )
    assert any("below" in reason for reason in zero["review_reasons"])


# ── P3：判定标准（合格线）身份进门禁 —— 两级阻断 ────────────────────────────


def _criteria(**overrides):
    criteria = {
        "algo": "sha256:canonical-json-of-dimensions/v1",
        "sha256": "a" * 64,
        "recognized": True,
        "reason": None,
    }
    criteria.update(overrides)
    return criteria


def test_bundle_records_that_verdict_criteria_were_not_evaluated():
    """**存在即校验**：不传就不评估，但必须记下"没评估"——`None` 不等于通过。"""
    result = evaluate_evidence_bundle(episodes=[_episode()])

    assert result["decision"] == "pass"
    assert result["evidence"]["verdict_criteria_present"] is False
    assert result["evidence"]["bands_identity"] is None


def test_bundle_reviews_unrecognized_bands_identity():
    """P3 验收①：**判定标准不可识别 ⇒ 不得 pass**（`unbanded` 不是零缺陷）。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_criteria=_criteria(
            recognized=False, sha256=None, reason="no_recognizable_bands"
        ),
    )

    assert result["decision"] == "review"
    assert any("unrecognized" in reason for reason in result["review_reasons"])
    assert "no_recognizable_bands" in " ".join(result["review_reasons"])


def test_bundle_reviews_identity_mismatch_against_expectation():
    """P3 验收②：**与预期不符 ⇒ review**——用了别的合格线，属可修的配置问题。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_criteria=_criteria(expected_sha256="b" * 16),
    )

    assert result["decision"] == "review"
    assert any("mismatch" in reason for reason in result["review_reasons"])


def test_bundle_holds_when_declared_identity_contradicts_recomputed():
    """P3 验收③：**声明与重算矛盾 ⇒ hold**——产物在自我声明上与事实不符。

    这一条与"与预期不符"分开：前者是**自相矛盾**（篡改/换版），后者只是配置没对上。
    """
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_criteria=_criteria(declared_sha256="c" * 64),
    )

    assert result["decision"] == "hold"
    assert any("contradicts declared value" in reason for reason in result["hard_failures"])


def test_bundle_still_passes_when_identity_matches():
    """**假阳性校准**：预期与声明都对得上时，不得因这条新检查变成 review。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_criteria=_criteria(expected_sha256="a" * 16, declared_sha256="a" * 64),
    )

    assert result["decision"] == "pass"
    assert result["evidence"]["verdict_criteria_present"] is True
    assert result["evidence"]["bands_identity"]["recognized"] is True


def test_bundle_passes_after_a_metadata_only_bands_edit(tmp_path):
    """计划验收例③（反向）：**改一句注释不改身份** ⇒ 门禁仍 pass（防过度阻断）。

    用**真实算法**算两遍：同一张维度表、只改 `note`，身份必须相同，门禁必须仍然 pass。
    """
    from eval_engine.core.verdict import bands_identity

    inner = {"tool_selection": {"pass_min": 4, "marginal_min": 3}}
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(
        json.dumps({"bands": inner, "note": "一稿"}, ensure_ascii=False), encoding="utf-8"
    )
    path_b.write_text(
        json.dumps({"bands": inner, "note": "二稿"}, ensure_ascii=False), encoding="utf-8"
    )

    identity = bands_identity(path_a)
    assert identity["sha256"] == bands_identity(path_b)["sha256"], "改注释不得改身份"

    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_criteria=dict(identity, expected_sha256=identity["sha256"]),
    )

    assert result["decision"] == "pass"


# ── 判定结果（决策级）进门禁：**证据 ≠ 政策** ──────────────────────────────


def _verdict_block(**overrides):
    block = {
        "label": "held_out",
        "n": 53,
        "judge_defect_rate": 0.321,
        "human_defect_rate": 0.359,  # 两个口径**分开放**，不得混成一个数
        "defect_rate_ci_item": [0.208, 0.453],
        "false_kill": 0,
        "false_pass": 2,
    }
    block.update(overrides)
    return block


def _verdict_evidence(blocks=None, **overrides):
    evidence = {
        "schema_version": "verdict-evidence/v1",
        "bands_identity": {
            "algo": "sha256:canonical-json-of-dimensions/v1",
            "sha256": "a" * 64,
            "recognized": True,
            "reason": None,
        },
        "blocks": [_verdict_block()] if blocks is None else blocks,
    }
    evidence.update(overrides)
    return evidence


def test_verdict_evidence_without_policy_cannot_pass():
    """**证据 ≠ 政策**：数字在、但没人说多少算不合格 ⇒ 不得判过。

    本模块**不设默认阈值**——"多少算不合格"是发布方的政策，不是实现细节。
    """
    result = evaluate_evidence_bundle(
        episodes=[_episode()], verdict_evidence=_verdict_evidence()
    )

    assert result["decision"] == "review"
    assert "no declared policy" in " ".join(result["review_reasons"])
    assert result["evidence"]["verdict_policy_declared"] is False


def test_verdict_evidence_within_policy_passes():
    """**假阳性校准**：在政策之内、身份也对得上 ⇒ 不得因这条新检查变成 review。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(),
        verdict_policy={"max_judge_defect_rate": 0.40, "max_false_pass": 2},
    )

    assert result["decision"] == "pass"
    assert result["evidence"]["verdict_evidence_present"] is True


def test_robust_overshoot_holds_but_straddling_ci_reviews():
    """**两级**：区间下界都超阈 ⇒ `hold`（稳健超标）；点估计超阈而区间跨阈 ⇒ `review`。"""
    held = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(
            blocks=[_verdict_block(judge_defect_rate=0.60, defect_rate_ci_item=[0.45, 0.74])]
        ),
        verdict_policy={"max_judge_defect_rate": 0.40},
    )
    assert held["decision"] == "hold"
    assert any("above policy" in reason for reason in held["hard_failures"])

    review = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(
            blocks=[_verdict_block(judge_defect_rate=0.42, defect_rate_ci_item=[0.30, 0.55])]
        ),
        verdict_policy={"max_judge_defect_rate": 0.40},
    )
    assert review["decision"] == "review"
    assert any("straddles" in reason for reason in review["review_reasons"])


def test_false_pass_above_policy_holds():
    """**漏杀**（人判缺陷而 Judge 放过）是发布门禁最该拦的方向 ⇒ 超限即 `hold`。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(),
        verdict_policy={"max_judge_defect_rate": 0.90, "max_false_pass": 0},
    )

    assert result["decision"] == "hold"
    assert any("false-pass above policy" in reason for reason in result["hard_failures"])


def test_insufficient_blocks_are_listed_and_cannot_support_a_verdict():
    """样本不足 ⇒ **不支持率结论**：不参与判定，但**必须显式列出**。

    否则"没算"又会被读成"没缺陷"——本仓那条纪律的同一个病。
    """
    thin = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(blocks=[_verdict_block(n=5)]),
        verdict_policy={"max_judge_defect_rate": 0.40},
    )
    assert thin["evidence"]["verdict_evidence"]["insufficient"] == [
        {"label": "held_out", "n": 5}
    ]
    assert thin["decision"] == "review"
    assert any("enough judged cells" in reason for reason in thin["review_reasons"])

    mixed = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(
            blocks=[_verdict_block(n=5), _verdict_block(label="dev", n=53)]
        ),
        verdict_policy={"max_judge_defect_rate": 0.40},
    )
    assert mixed["evidence"]["verdict_evidence"]["insufficient"] == [
        {"label": "held_out", "n": 5}
    ]
    assert mixed["decision"] == "pass"


def test_verdict_evidence_carries_the_criteria_identity_into_the_same_check():
    """判定结果里自带的合格线身份 → 走 P3 的**同一套**检查（不另立一套口径）。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(
            bands_identity={"recognized": False, "sha256": None, "reason": "unreadable"}
        ),
        verdict_policy={"max_judge_defect_rate": 0.90},
    )

    assert result["decision"] == "review"
    assert any("bands identity unrecognized" in r for r in result["review_reasons"])


def test_unsupported_verdict_evidence_schema_holds():
    """与其它证据块同一约定：schema 不匹配 ⇒ `hold`。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(schema_version="verdict-evidence/v0"),
        verdict_policy={"max_judge_defect_rate": 0.90},
    )

    assert result["decision"] == "hold"
    assert "unsupported verdict evidence schema" in result["hard_failures"]


def test_verdict_evidence_without_a_bands_identity_cannot_pass():
    """**补的一刀**：判定结果证据在场、却指不出合格线 ⇒ 不得判过。

    否则"没配身份"就在这条新路径上**静默放行**——能力在、却没人查（P3 那个病的同构体）。
    """
    evidence = _verdict_evidence()
    evidence.pop("bands_identity")
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=evidence,
        verdict_policy={"max_judge_defect_rate": 0.90},
    )

    assert result["decision"] == "review"
    assert any("no recognizable bands identity" in r for r in result["review_reasons"])


def test_unrecognizable_identity_is_reported_once_by_the_shared_check():
    """带 `recognized=False` 的身份**不算"空手来"**：由 P3 那段报出来，**不重复报两条**。"""
    result = evaluate_evidence_bundle(
        episodes=[_episode()],
        verdict_evidence=_verdict_evidence(
            bands_identity={"recognized": False, "sha256": None, "reason": "unreadable"}
        ),
        verdict_policy={"max_judge_defect_rate": 0.90},
    )

    reasons = result["review_reasons"]
    assert any("bands identity unrecognized" in r for r in reasons)
    assert not any("no recognizable bands identity" in r for r in reasons), "别重复报"
