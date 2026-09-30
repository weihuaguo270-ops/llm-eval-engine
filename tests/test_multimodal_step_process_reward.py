"""Vertical slice: multimodal as trajectory steps, not generation leaderboard."""

from __future__ import annotations

import json
from pathlib import Path

from eval_engine.core.dynamic_rubric import build_step_context, generate_rubrics_for_step
from eval_engine.core.failure_taxonomy import classify_step_failure, summarize_failures
from eval_engine.core.multimodal_step import (
    analyze_multimodal_steps,
    extract_step_artifacts,
    process_quality_from_report,
)
from eval_engine.core.process_reward import ProcessRewardScorer
from eval_engine.core.trajectory_parser import parse_trajectory
from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "fixtures" / "episodes"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mock_judge(prompt: str) -> dict:
    """Frozen judge：多模态步给中高分，由 multimodal_step findings 负责扣分。"""
    if "类型: action" in prompt and (
        "generate_image" in prompt or "describe_image" in prompt
    ):
        return {
            "role_understanding": "多模态工具步",
            "rubrics": [
                {
                    "dimension": "media_timing",
                    "criteria": "时机",
                    "score": 4.0,
                    "reason": "judge baseline",
                },
                {
                    "dimension": "media_arg_fidelity",
                    "criteria": "参数",
                    "score": 4.0,
                    "reason": "judge baseline",
                },
            ],
            "step_score": 4.0,
            "needs_revision": False,
        }
    if "类型: final" in prompt:
        return {
            "role_understanding": "终态",
            "rubrics": [
                {
                    "dimension": "completeness",
                    "criteria": "完整",
                    "score": 4.0,
                    "reason": "ok",
                }
            ],
            "step_score": 4.0,
            "needs_revision": False,
        }
    return {
        "role_understanding": "普通步",
        "rubrics": [
            {
                "dimension": "general",
                "criteria": "通用",
                "score": 4.0,
                "reason": "ok",
            }
        ],
        "step_score": 4.0,
        "needs_revision": False,
    }


def test_parse_preserves_artifacts_and_step_kind():
    episode = _load("multimodal_step_ok.json")
    dag = parse_trajectory(episode["trajectory"])
    gen = dag.get_node(1)
    assert gen is not None
    assert gen.tool_name == "generate_image"
    assert gen.metadata.get("step_kind") == "generate_image"
    arts = extract_step_artifacts(gen)
    assert len(arts) == 1
    assert arts[0].id == "login_blue_button"
    assert arts[0].sha256 == (
        "0b457c939a634c18a4b31332846b0f6fd96237b3c346fd36fb7f2c97ac96a9ad"
    )
    assert arts[0].uri.endswith("login_blue_button.png")


def test_multimodal_action_rubrics_include_process_dimensions():
    episode = _load("multimodal_step_ok.json")
    dag = parse_trajectory(episode["trajectory"])
    ctx = build_step_context(dag, 1)
    dims = {r.dimension for r in generate_rubrics_for_step(ctx)}
    assert "media_timing" in dims
    assert "media_arg_fidelity" in dims
    assert "artifact_attachment" in dims
    assert "media_safety" in dims


def test_ok_episode_passes_process_quality_gate():
    episode = _load("multimodal_step_ok.json")
    dag = parse_trajectory(episode["trajectory"])
    findings = analyze_multimodal_steps(dag, require_vision=True)
    assert findings == []
    scorer = ProcessRewardScorer(
        judge_fn=_mock_judge, enable_trace_findings=False
    )
    report = scorer.score_trajectory(
        dag, trajectory=episode["trajectory"], extra_findings=findings
    )
    assert report.overall_score >= 3.5
    pq = process_quality_from_report(
        report, case_id=episode["episode_id"], multimodal_findings=findings
    )
    # D2：报告总分是「已评分步的加权均值」，与门禁值（媒体步 min）不是同一个口径。
    assert pq["overall_score_scope"] == "all_scored_steps_weighted"
    decision = evaluate_evidence_bundle(
        episodes=[episode],
        process_quality=pq,
    )
    assert decision["decision"] == "pass"
    assert decision["evidence"]["process_quality_present"] is True


def test_bad_episode_attributes_multimodal_failures_and_reviews():
    episode = _load("multimodal_step_bad.json")
    dag = parse_trajectory(episode["trajectory"])
    findings = analyze_multimodal_steps(dag, require_vision=False)
    codes = {f.failure_type for f in findings}
    assert "unnecessary_generation" in codes
    assert "wrong_media_args" in codes

    scorer = ProcessRewardScorer(
        judge_fn=_mock_judge, enable_trace_findings=False
    )
    report = scorer.score_trajectory(
        dag, trajectory=episode["trajectory"], extra_findings=findings
    )
    assert report.needs_revision is True
    assert report.overall_score < 3.5

    summary = summarize_failures(
        [(episode["episode_id"], "multimodal_step", report)]
    )
    assert summary.by_type.get("unnecessary_generation", 0) >= 1
    # 同一步多条 finding 时 taxonomy 取 structured 首条；其余仍在 check_findings
    finding_types = {f["failure_type"] for f in (report.check_findings or [])}
    assert "wrong_media_args" in finding_types or "wrong_media_args" in {
        f.failure_type for f in findings
    }

    # structured failure_type 保留在根因步
    gen_step = next(s for s in report.per_step if s.tool_name == "generate_image")
    rec = classify_step_failure(
        gen_step, error_sources=report.error_sources, case_id=episode["episode_id"]
    )
    assert rec is not None
    assert rec.failure_type in {
        "unnecessary_generation",
        "wrong_media_args",
    }

    pq = process_quality_from_report(
        report, case_id=episode["episode_id"], multimodal_findings=findings
    )
    decision = evaluate_evidence_bundle(
        episodes=[episode],
        process_quality=pq,
    )
    # 过程分不足 → review（非 CLIP 成对显著差）
    assert decision["decision"] == "review"
    assert any("process score" in r for r in decision["review_reasons"])


def test_media_step_without_evidence_is_unscored_not_root_cause():
    """C8 回归：媒体步无评分证据 → 需要修订（门禁不变），但不得被归因为根因。

    旧行为给该步一个中性的 context=3.0，而 3.0 < min_step_score(3.5)，
    于是「没有评分证据」被当成「低分失败步」，并成为 error_sources 的根因。
    """
    from eval_engine.core.multimodal_process_judge import (
        _is_media_step,
        judge_multimodal_step,
    )
    from eval_engine.core.trajectory_parser import parse_trajectory

    dag = parse_trajectory({
        "query": "生成一张登录页截图",
        "steps": [
            {"step_index": 0, "type": "thought", "content": "计划"},
            {"step_index": 1, "type": "action",
             "action": {"name": "generate_image", "args": {"prompt": "login"}},
             "content": "generate_image", "observation": "ok"},
            {"step_index": 2, "type": "final", "content": "done"},
        ],
        "total_steps": 3,
        "final_answer": "done",
    })
    node = next(n for n in dag.nodes if n.step_index == 1)
    assert _is_media_step(node), "夹具未生效：该步应为媒体步"

    result = judge_multimodal_step(node, dag)
    assert result["needs_revision"] is True, "无评分证据仍不得据此通过"
    assert "step_score" not in result, "未评估的步不得给出中性低分"


def test_thought_step_is_not_applicable():
    """方案 C：思考步不在媒体过程评分范围内——夹具里遗留的 context 值不再计分。"""
    from eval_engine.core.multimodal_process_judge import judge_multimodal_step
    from eval_engine.core.trajectory_parser import parse_trajectory

    dag = parse_trajectory({
        "query": "生成一张登录页截图",
        "steps": [
            {"step_index": 0, "type": "thought", "thought": "计划",
             "judge_scores": {"context": 5}},
            {"step_index": 1, "type": "final", "content": "done",
             "judge_scores": {"media_timing": 5, "media_arg_fidelity": 5,
                              "artifact_attachment": 5, "media_safety": 5}},
        ],
        "total_steps": 2,
        "final_answer": "done",
    })
    thought = next(n for n in dag.nodes if n.step_index == 0)
    result = judge_multimodal_step(thought, dag)

    assert result["applicable"] is False, "思考步应标记为不适用"
    assert "step_score" not in result, "不适用步不得给分"
    assert result.get("needs_revision") is not True, "不适用步不得触发修订"

