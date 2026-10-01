"""Tests for trace-debugger findings adapter and eval contracts."""

from __future__ import annotations

from eval_engine.core.eval_contracts import EvalContract, evaluate_eval_contracts
from eval_engine.core.failure_taxonomy import classify_step_failure
from eval_engine.core.process_reward import ProcessRewardScorer, RubricResult, StepScore
from eval_engine.core.trajectory_parser import parse_trajectory
from eval_engine.integrations.trace_findings import (
    analyze_trajectory_findings,
    map_trace_failure_type,
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
    assert bad.step_score == 4.5
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


# ── 回归：检索类失败必须保留自己的类型 ──
# 旧行为：search_empty→wrong_tool、search_timeout→other、search_weak 无条目落 other。


SEARCH_EMPTY_ANALYSIS = {
    "session_id": "golden_search_empty",
    "needs_fix": True,
    "paths": [
        {
            "failures": ["search_empty"],
            "steps": [
                {
                    "step_index": 1,
                    "action": "web_search",
                    "failure_type": "search_empty",
                    "failure_detail": "web_search returned no results",
                }
            ],
        }
    ],
}


def _search_traj() -> dict:
    return {
        "session_id": "t-search",
        "query": "usd cny rate today",
        "steps": [
            {
                "step": 1,
                "thought": "search the rate",
                "action": {"name": "web_search", "arguments": "{\"q\": \"usd cny\"}"},
                "observation": "",
            },
            {
                "step": 2,
                "thought": "FINAL ANSWER: 712",
                "observation": "",
            },
        ],
        "final_answer": "712",
    }


def test_search_failure_types_map_to_themselves():
    """检索类不再被换算成 wrong_tool / other；大小写不敏感。"""
    for raw in ("search_empty", "search_weak", "search_timeout"):
        assert map_trace_failure_type(raw) == raw
    assert map_trace_failure_type("SEARCH_EMPTY") == "search_empty"
    assert map_trace_failure_type(" unknown_search_rule ") == "other"


def test_search_failure_survives_process_reward_and_taxonomy():
    """端到端：trace 检索失败 → step.failure_type → taxonomy.by_type 全程保型。"""

    def _judge(prompt: str) -> dict:
        score = 1.0 if "web_search" in prompt else 4.5
        return {
            "role_understanding": "",
            "rubrics": [],
            "step_score": score,
            "needs_revision": score < 3.5,
        }

    dag = parse_trajectory(_search_traj())
    scorer = ProcessRewardScorer(judge_fn=_judge, min_step_score=3.5)
    report = scorer.score_trajectory(dag, trace_analysis=SEARCH_EMPTY_ANALYSIS)

    bad = next(s for s in report.per_step if s.step_index == 0)
    assert bad.failure_type == "search_empty"
    assert "trace_debugger" in bad.check_sources

    from eval_engine.core.failure_taxonomy import summarize_failures

    summary = summarize_failures([("c1", "search", report)])
    assert summary.by_type.get("search_empty") == 1
    assert summary.by_type.get("wrong_tool", 0) == 0
    assert summary.by_type.get("other", 0) == 0
