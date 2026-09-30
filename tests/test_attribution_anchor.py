"""attribution_anchor — 确定性失败步与 error_sources 的必要条件校验"""

from eval_engine.core.attribution_anchor import (
    anchor_steps,
    cross_check_attribution,
    format_cross_check,
    summarize_cross_checks,
)
from eval_engine.core.process_reward import ProcessRewardScorer
from eval_engine.core.trajectory_parser import parse_trajectory


def _analysis(failure_type: str, step_index: int) -> dict:
    """trace-debugger analysis_to_dict 形状；step_index 为 Format B 的 1-based。"""
    return {
        "session_id": "a",
        "needs_fix": True,
        "paths": [
            {
                "failures": [failure_type],
                "steps": [
                    {
                        "failure_type": failure_type,
                        "step_index": step_index,
                        "action": "calculator",
                        "failure_detail": "test fixture",
                    }
                ],
            }
        ],
    }


def _trajectory() -> dict:
    return {
        "query": "计算 1+1",
        "steps": [
            {"step_index": 0, "type": "action",
             "action": {"name": "calculator", "args": {"expression": "1+1"}},
             "content": "calculator"},
            {"step_index": 1, "type": "final", "content": "2"},
        ],
        "total_steps": 2,
        "final_answer": "2",
    }


class _Report:
    """最小替身：只暴露 error_sources。"""

    def __init__(self, sources):
        self.error_sources = list(sources)


def test_anchor_steps_normalize_to_zero_based():
    """Format B 的 step_index=2 → 0-based 1，与 error_sources 同尺度。"""
    assert anchor_steps(analysis=_analysis("tool_error", 2)) == {1: ["tool_error"]}


def test_non_anchor_types_are_ignored():
    """no_answer / llm_offtrack 挂在最后一步，不是定位主张 → 不作锚点。"""
    assert anchor_steps(analysis=_analysis("llm_offtrack", 2)) == {}
    assert anchor_steps(analysis=_analysis("no_answer", 2)) == {}


def test_findings_without_step_index_are_not_anchors():
    analysis = {
        "session_id": "a",
        "needs_fix": True,
        "paths": [{"failures": ["search_empty"], "steps": []}],
    }
    assert anchor_steps(analysis=analysis) == {}


def test_cross_check_agrees_when_source_covers_anchor():
    result = cross_check_attribution(
        _Report([1, 0]), analysis=_analysis("tool_error", 2), episode_id="ep-ok"
    )
    assert result["anchor_total"] == 1
    assert result["anchor_hit"] == 1
    assert result["missed_steps"] == []
    # step 0 没有确定性锚点：它归因得对不对需要人工标注，不计入必要条件通过率
    assert result["unaided_sources"] == [0]


def test_cross_check_flags_missed_anchor():
    result = cross_check_attribution(
        _Report([0]), analysis=_analysis("tool_error", 2), episode_id="ep-miss"
    )
    assert result["missed_steps"] == [1]
    summary = summarize_cross_checks([result])
    assert summary["anchor_consistency"] == 0.0
    assert summary["misses"] == [{"episode_id": "ep-miss", "steps": [1]}]
    assert "必要条件" in format_cross_check(summary)


def test_summary_without_anchors_reports_no_number():
    result = cross_check_attribution(
        _Report([0]), analysis=_analysis("llm_offtrack", 2), episode_id="e0"
    )
    summary = summarize_cross_checks([result])
    assert summary["anchor_total"] == 0
    assert summary["anchor_consistency"] is None
    assert "无可用锚点" in format_cross_check(summary)


def test_scorer_error_sources_agree_with_anchor_end_to_end():
    """端到端：Judge 把硬失败步评为低分时，锚点必须落在 error_sources 里。"""

    def _judge(prompt: str) -> dict:
        score = 1.0 if "类型: action" in prompt else 4.0
        return {
            "role_understanding": "",
            "rubrics": [],
            "step_score": score,
            "needs_revision": score < 3.5,
        }

    analysis = _analysis("tool_error", 1)
    dag = parse_trajectory(_trajectory())
    scorer = ProcessRewardScorer(judge_fn=_judge, min_step_score=3.5)
    report = scorer.score_trajectory(dag, trace_analysis=analysis)

    assert report.error_sources == [0]
    result = cross_check_attribution(report, analysis=analysis, episode_id="ep-e2e")
    assert result["anchor_hit"] == 1
    assert summarize_cross_checks([result])["anchor_consistency"] == 1.0
