"""Tests for trace-debugger findings adapter and eval contracts."""

from __future__ import annotations

from eval_engine.core.eval_contracts import EvalContract, evaluate_eval_contracts
from eval_engine.core.failure_taxonomy import classify_step_failure
from eval_engine.core.process_reward import ProcessRewardScorer, RubricResult, StepScore
from eval_engine.core.trajectory_parser import parse_trajectory
from eval_engine.integrations.trace_findings import (
    analyze_trajectory_findings,
    normalize_analysis_dict,
)


TOOL_ERROR_ANALYSIS = {
    "session_id": "golden_tool_error",
    "needs_fix": True,
    "fix_suggestions": ["fix tool args"],
    "paths": [
        {
            "failures": ["tool_error"],
            "steps": [
                {
                    "step_index": 1,
                    "action": "calculator",
                    "failure_type": "tool_error",
                    "failure_detail": "calculator failed: bad expression",
                    "suggestion": "check args",
                },
                {
                    "step_index": 2,
                    "action": "",
                    "failure_type": "",
                    "failure_detail": "",
                    "suggestion": "",
                },
            ],
        }
    ],
}


def _traj() -> dict:
    return {
        "session_id": "t1",
        "query": "计算 2+2",
        "steps": [
            {
                "step": 1,
                "thought": "use calculator",
                "action": {"name": "calculator", "arguments": "{\"expression\": \"2++\"}"},
                "observation": "{\"error\": \"bad\"}",
            },
            {
                "step": 2,
                "thought": "FINAL ANSWER: fail",
                "observation": "",
            },
        ],
        "final_answer": "fail",
    }


def _good_judge(_prompt: str) -> dict:
    return {
        "role_understanding": "ok",
        "rubrics": [
            {"dimension": "general", "criteria": "g", "score": 4.5, "reason": "ok"}
        ],
        "step_score": 4.5,
        "needs_revision": False,
    }


def test_normalize_analysis_maps_trace_failure():
    report = normalize_analysis_dict(TOOL_ERROR_ANALYSIS)
    assert report.needs_fix is True
    assert report.failure_types == ["tool_error"]
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.source == "trace_debugger"
    assert finding.failure_type == "wrong_params"
    assert finding.step_index == 0  # 1-based -> 0-based


def test_eval_contract_forbidden_and_expected_tools():
    dag = parse_trajectory(_traj())
    findings = evaluate_eval_contracts(
        dag,
        EvalContract(
            expected_tools_any=("web_search",),
            forbidden_tools=("calculator",),
            require_nonempty_final=True,
        ),
    )
    codes = {f.code for f in findings}
    assert "forbidden_tool" in codes
    assert "missing_expected_tool_any" in codes
    assert all(f.source == "eval_contract" for f in findings)


def test_process_reward_consumes_trace_findings_without_local_debugger_rules():
    dag = parse_trajectory(_traj())
    scorer = ProcessRewardScorer(
        judge_fn=_good_judge,
        eval_contract=EvalContract(forbidden_tools=("read_secret",)),
        enable_trace_findings=True,
    )
    report = scorer.score_trajectory(
        dag,
        trajectory=_traj(),
        trace_analysis=TOOL_ERROR_ANALYSIS,
    )
    assert report.needs_revision is True
    assert report.check_findings
    assert any(f["source"] == "trace_debugger" for f in report.check_findings)
    # no local behavior heuristics invented here
    assert not any(
        f["code"].startswith("behavior:") for f in report.check_findings
    )
    bad = next(s for s in report.per_step if s.step_index == 0)
    assert bad.needs_revision is True
    assert bad.failure_type == "wrong_params"
    assert "trace_debugger" in bad.check_sources


def test_taxonomy_prefers_structured_failure_type():
    step = StepScore(
        step_index=0,
        step_type="action",
        tool_name="calculator",
        rubrics=[
            RubricResult(
                "check:trace:tool_error",
                "calculator failed",
                1.0,
                "calculator failed",
                True,
                "trace_debugger",
            )
        ],
        step_score=1.0,
        needs_revision=True,
        failure_type="wrong_params",
        check_sources=["trace_debugger"],
    )
    rec = classify_step_failure(step, error_sources=[0], case_id="c1")
    assert rec is not None
    assert rec.failure_type == "wrong_params"


def test_analyze_trajectory_findings_accepts_offline_analysis():
    report = analyze_trajectory_findings(_traj(), analysis=TOOL_ERROR_ANALYSIS)
    assert report.findings[0].raw_failure_type == "tool_error"
