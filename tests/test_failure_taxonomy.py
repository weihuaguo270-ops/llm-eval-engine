"""Tests for failure taxonomy aggregation"""

from eval_engine.core.failure_taxonomy import summarize_failures
from eval_engine.core.process_reward import ProcessRewardReport, StepScore, RubricResult


def _report(steps: list[StepScore], sources: list[int]) -> ProcessRewardReport:
    return ProcessRewardReport(
        query="q",
        per_step=steps,
        overall_score=2.5,
        num_steps=len(steps),
        num_scored=len(steps),
        num_failed_steps=sum(1 for s in steps if s.needs_revision),
        error_sources=sources,
        needs_revision=True,
        healing_log=[],
        dag_summary={},
    )


def test_summarize_failures_by_type():
    steps = [
        StepScore(
            step_index=0,
            step_type="action",
            tool_name="web_search",
            rubrics=[
                RubricResult("tool_selection", "t", 2.0, "工具选择错误", True),
            ],
            step_score=2.0,
            needs_revision=True,
        ),
        StepScore(
            step_index=1,
            step_type="final",
            tool_name=None,
            rubrics=[
                RubricResult("general", "g", 2.0, "基于不完整数据", True),
            ],
            step_score=2.0,
            needs_revision=True,
        ),
    ]
    rep = _report(steps, [0])
    summary = summarize_failures([("c1", "tool", rep)])
    assert summary.total_failures == 2
    assert summary.by_type.get("wrong_tool", 0) >= 1
    assert summary.by_type.get("error_propagation", 0) >= 1
    print(f"[PASS] summary types={summary.by_type}")
