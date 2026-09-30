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


def test_unscored_step_is_not_error_propagation():
    """未评估步（无评分证据）不得被归为下游错误传播。"""
    from eval_engine.core.failure_taxonomy import classify_step_failure

    step = StepScore(
        step_index=1,
        step_type="action",
        tool_name="generate_image",
        rubrics=[],
        step_score=0.0,
        needs_revision=True,
    )
    rec = classify_step_failure(step, error_sources=[0], case_id="c1")
    assert rec is not None, "未评估步仍应出现在归类中（供人工补评分）"
    assert rec.failure_type == "unscored"
    assert rec.is_root_cause is False


def test_not_applicable_step_is_not_a_failure():
    """不适用步（思考步）不属于失败归类范围。"""
    from eval_engine.core.failure_taxonomy import classify_step_failure

    step = StepScore(
        step_index=0,
        step_type="thought",
        tool_name=None,
        rubrics=[],
        step_score=0.0,
        needs_revision=False,
        applicable=False,
    )
    assert classify_step_failure(step, error_sources=[1], case_id="c1") is None
