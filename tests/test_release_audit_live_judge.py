"""Live Judge soft dimensions for release-audit media steps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_engine.core.failure_taxonomy import classify_step_failure
from eval_engine.core.multimodal_process_judge import (
    DIMENSIONS,
    extract_dimension_scores,
    make_live_dimension_judge,
)
from eval_engine.core.multimodal_step import process_quality_from_report
from eval_engine.core.process_reward import ProcessRewardScorer
from eval_engine.gates.release_audit import (
    audit_release,
    rebuild_held_out_calibration,
)
from eval_engine.integrations.episode import import_episode
from eval_engine.core.trajectory_parser import parse_trajectory

ROOT = Path(__file__).resolve().parents[1]
OK = ROOT / "examples" / "fixtures" / "episodes" / "multimodal_step_ok.json"
CALIBRATION = (
    ROOT / "examples" / "fixtures" / "calibration" / "multimodal_dimension_held_out.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _mock_llm(fixed: dict[str, float]):
    calls: list[str] = []

    def call(prompt: str) -> dict:
        calls.append(prompt)
        return {
            "role_understanding": "media step",
            "rubrics": [
                {
                    "dimension": name,
                    "score": fixed[name],
                    "reason": "mock",
                }
                for name in DIMENSIONS
            ],
            "step_score": sum(fixed.values()) / len(fixed),
            "needs_revision": False,
        }

    call.calls = calls  # type: ignore[attr-defined]
    return call


def test_live_judge_scores_media_steps_and_skips_thought():
    raw = _load(OK)
    dag = parse_trajectory(import_episode(raw).trajectory)
    # Pre-filled fixture scores must not leak into live mode.
    for node in dag.nodes:
        if node.tool_name == "generate_image":
            node.metadata["judge_scores"] = {
                "media_timing": 1,
                "media_arg_fidelity": 1,
                "artifact_attachment": 1,
                "media_safety": 1,
            }
    fixed = {
        "media_timing": 4,
        "media_arg_fidelity": 4,
        "artifact_attachment": 4,
        "media_safety": 5,
    }
    llm = _mock_llm(fixed)
    judge = make_live_dimension_judge(dag, llm)
    results = [judge("ignored") for _ in dag.nodes]
    thought = results[0]
    # 方案 C：思考步不适用——不再伪造 context 分，也不触发修订
    assert thought["applicable"] is False
    assert thought["rubrics"] == []
    assert "step_score" not in thought
    assert thought.get("needs_revision") is not True
    assert len(llm.calls) == 3  # generate + describe + final
    for result in results[1:]:
        assert [r["dimension"] for r in result["rubrics"]] == list(DIMENSIONS)
        assert [r["score"] for r in result["rubrics"]] == [4.0, 4.0, 4.0, 5.0]
    media_node = next(n for n in dag.nodes if n.tool_name == "generate_image")
    assert media_node.metadata["judge_scores"] == {
        "media_timing": 4.0,
        "media_arg_fidelity": 4.0,
        "artifact_attachment": 4.0,
        "media_safety": 5.0,
    }


def test_incomplete_live_dimensions_degrade_to_unscored_not_a_crash():
    """D3：live Judge 少给维度时按步降级为「未评估 + judge_error」。

    拒绝的方案是「缺维度就给部分学分」：那会把判分器的输入错误伪装成低分证据，
    进而污染 error_sources 归因。这里钉住的是：整条不崩、不伪造分数、总分标记为不可用。
    """
    raw = _load(OK)
    dag = parse_trajectory(import_episode(raw).trajectory)

    def partial_llm(_prompt: str) -> dict:
        return {
            "role_understanding": "media step",
            "rubrics": [{"dimension": "media_timing", "score": 4}],
            "step_score": 4.0,
            "needs_revision": False,
        }

    report = ProcessRewardScorer(
        judge_fn=make_live_dimension_judge(dag, partial_llm),
        enable_trace_findings=False,
    ).score_trajectory(dag)

    assert report.num_scored == 0
    assert report.scored is False
    assert report.needs_revision is True
    assert report.error_sources == []
    affected = [step for step in report.per_step if step.applicable]
    assert affected and all(step.step_score == 0.0 for step in affected)
    assert all("missing dimensions" in (step.role_understanding or "") for step in affected)
    records = [
        classify_step_failure(step, error_sources=report.error_sources, case_id="mm-ok")
        for step in report.per_step
    ]
    assert [record.failure_type for record in records if record] == ["judge_error"] * len(affected)
    quality = process_quality_from_report(report, case_id="mm-ok")
    assert quality["overall_score"] is None
    assert quality["overall_score_scope"] == "all_scored_steps_weighted"


def test_live_scores_against_fixture_calibration_stay_uncalibrated():
    raw = _load(OK)
    fixed = {
        "media_timing": 1,
        "media_arg_fidelity": 1,
        "artifact_attachment": 1,
        "media_safety": 1,
    }
    report = audit_release(
        [raw],
        judge_factory=lambda dag: make_live_dimension_judge(dag, _mock_llm(fixed)),
        calibration=_load(CALIBRATION),
    )
    assert report["decision_basis"] == "uncalibrated"
    assert report["process_quality"] is None
    assert report["decision"] == "review"


def test_rebuild_calibration_binds_live_scores_into_gate():
    raw = _load(OK)
    fixed = {
        "media_timing": 5,
        "media_arg_fidelity": 4,
        "artifact_attachment": 5,
        "media_safety": 5,
    }
    report = audit_release(
        [raw],
        judge_factory=lambda dag: make_live_dimension_judge(dag, _mock_llm(fixed)),
        calibration=_load(CALIBRATION),
        rebuild_calibration=True,
    )
    assert report["decision_basis"] == "process_reward_soft_dimensions"
    assert report["calibration"]["sample_size"] == 12
    assert isinstance(report["calibration"]["kappa"], float)
    assert report["calibration"]["kappa_unit"] == "dimension_cell"
    assert report["calibration"]["bootstrap"]["kappa"]["low"] <= report["calibration"]["bootstrap"]["kappa"]["high"]
    assert report["process_quality"] is not None
    rebuilt = report["rebuilt_calibration"]
    assert rebuilt is not None
    live_rows = [
        row
        for row in rebuilt["items"]
        if row["step_index"] == 1 and row["dimension"] == "media_timing"
    ]
    assert live_rows[0]["judge_score"] == 5.0
    assert live_rows[0]["human_score"] is not None


def test_extract_dimension_scores_requires_all_four():
    with pytest.raises(ValueError, match="missing dimensions"):
        extract_dimension_scores(
            {"rubrics": [{"dimension": "media_timing", "score": 4}]}
        )


def test_rebuild_held_out_calibration_helper():
    prior = _load(CALIBRATION)
    cells = {
        "mm-step-read-write-ok-001": [
            (1, "media_timing", 2.0),
            (1, "media_arg_fidelity", 2.0),
            (1, "artifact_attachment", 2.0),
            (1, "media_safety", 2.0),
            (2, "media_timing", 2.0),
            (2, "media_arg_fidelity", 2.0),
            (2, "artifact_attachment", 2.0),
            (2, "media_safety", 2.0),
            (3, "media_timing", 2.0),
            (3, "media_arg_fidelity", 2.0),
            (3, "artifact_attachment", 2.0),
            (3, "media_safety", 2.0),
        ]
    }
    rebuilt = rebuild_held_out_calibration(prior, cells)
    assert all(row["judge_score"] == 2.0 for row in rebuilt["items"])
    assert len(rebuilt["items"]) == 12
