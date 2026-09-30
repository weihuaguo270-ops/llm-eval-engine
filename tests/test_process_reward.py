"""测试 process_reward + eval_loop 集成流程

使用模拟的 Judge 函数测试评分流程和错误分析。
"""

import sys
import os


from eval_engine.core.trajectory_parser import parse_trajectory
from eval_engine.core.process_reward import (
    ProcessRewardScorer,
    analyze_error_propagation,
    pack_revision_instructions,
)


def _mock_judge(prompt: str) -> dict:
    """模拟 Judge LLM 调用

    根据步骤类型（%5B 即 [ 的编码形式）区分评分结果。
    实际场景中，prompt 里会包含 [thought]、[action]、[observation]、[final]。
    """
    step_type_markers = {
        "thought": ("thought", 3.5, False, ["推理基本正确"]),
        "action": ("action", 4.25, False, ["选择了合适的工具", "参数合理"]),
        "observation": ("observation", 4.0, False, ["正确解读了返回结果"]),
        "final": ("final", 2.5, True, ["遗漏了关键信息", "部分基于搜索结果"]),
    }
    for marker, (_, score, needs_rev, reasons) in step_type_markers.items():
        type_marker = f"类型: {marker}"
        if type_marker in prompt:
            rubrics = [
                {"dimension": f"{marker}_quality", "criteria": f"{marker} 质量",
                 "score": score, "reason": reasons[i] if i < len(reasons) else "合格"}
                for i in range(len(reasons))
            ]
            return {
                "role_understanding": f"Agent 执行 {marker} 步骤",
                "rubrics": rubrics if rubrics else [{"dimension": "general", "criteria": "通用", "score": 3.0, "reason": "无明显问题"}],
                "step_score": score,
                "needs_revision": needs_rev,
            }
    return {
        "role_understanding": "未知步骤",
        "rubrics": [{"dimension": "general", "criteria": "通用", "score": 3.0, "reason": "无明显问题"}],
        "step_score": 3.0,
        "needs_revision": False,
    }


def _mock_bad_judge(prompt: str) -> dict:
    """模拟有错误的步骤（action 步骤有误导致 cascade）"""
    if "类型: action" in prompt:
        return {
            "role_understanding": "工具调用失败",
            "rubrics": [
                {"dimension": "tool_selection", "criteria": "工具选择", "score": 1.0, "reason": "工具参数错误，调用失败"},
                {"dimension": "argument_quality", "criteria": "参数质量", "score": 1.0, "reason": "参数为编造值"},
            ],
            "step_score": 1.0,
            "needs_revision": True,
        }
    return _mock_judge(prompt)


def test_process_reward_good():
    """正常评分的 Process Reward"""
    trajectory = {
        "session_id": "traj_test_pr_01",
        "query": "搜索Python的sort函数用法并总结",
        "steps": [
            {"step_index": 0, "type": "thought",
             "content": "先搜索Python sort函数用法"},
            {"step_index": 1, "type": "action",
             "action": {"name": "web_search", "args": {"query": "Python sort"}},
             "content": "web_search..."},
            {"step_index": 2, "type": "observation",
             "content": "搜索结果：sort()是列表内置方法...",
             "observation": "搜索结果：sort()是列表内置方法..."},
            {"step_index": 3, "type": "final",
             "content": "Python的sort()方法用于列表原地排序..."},
        ],
        "total_steps": 4,
        "final_answer": "Python的sort()方法用于列表原地排序...",
    }

    dag = parse_trajectory(trajectory)
    scorer = ProcessRewardScorer(judge_fn=_mock_judge, min_step_score=3.5)
    report = scorer.score_trajectory(dag, fast_mode=False)

    print(f"总分: {report.overall_score:.3f}")
    print(f"失败步骤: {report.num_failed_steps}")
    print(f"需修正: {report.needs_revision}")
    for s in report.per_step:
        print(f"  Step {s.step_index} [{s.step_type}]: {s.step_score:.2f} {'❌' if s.needs_revision else '✅'}")

    assert report.num_scored == 4
    assert report.num_failed_steps >= 1  # final step fails in mock

    # 错误传播分析
    error_analysis = analyze_error_propagation(report, dag)
    print(f"错误源头: {error_analysis['error_sources']}")

    # 修正指令
    fix = pack_revision_instructions(report, dag)
    print(f"\n修正指令预览:\n{fix[:300]}...")
    assert "需修正" in fix or "修正" in fix or "评估" in fix

    print("✅ test_process_reward_good passed")


def test_iteration_improvement():
    """模拟两次迭代分数提升"""
    trajectory = {
        "session_id": "traj_test_iter",
        "query": "计算 (23+45)*2",
        "steps": [
            {"step_index": 0, "type": "thought", "content": "先计算"},
            {"step_index": 1, "type": "action",
             "action": {"name": "calculator", "args": {"expression": "(23+45)*2"}},
             "content": "calculator"},
            {"step_index": 2, "type": "observation",
             "content": "136", "observation": "136"},
            {"step_index": 3, "type": "final",
             "content": "结果是136"},
        ],
        "total_steps": 4,
        "final_answer": "结果是136",
    }

    dag = parse_trajectory(trajectory)
    scorer = ProcessRewardScorer(judge_fn=_mock_judge)
    report = scorer.score_trajectory(dag)

    print(f"\n[迭代测试] 总分: {report.overall_score:.3f}")
    if report.needs_revision:
        fix = pack_revision_instructions(report, dag)
        print(f"修正指令长度: {len(fix)} 字符")

    print("✅ test_iteration_improvement passed")


def test_error_sources_share_the_revision_threshold():
    """回归：根因定位必须与 needs_revision 共用阈值

    修复前 find_error_sources() 使用默认 3.0，而 min_step_score=3.5：得分为 3.2 的
    失败步会被标记 needs_revision，却永远不可能被判为根因（error_sources 为空）。
    """
    trajectory = {
        "session_id": "traj_threshold_split",
        "query": "计算 1+1",
        "steps": [
            {"step_index": 0, "type": "action",
             "action": {"name": "calculator", "args": {"expression": "1+1"}},
             "content": "calculator"},
            {"step_index": 1, "type": "final", "content": "结果是2"},
        ],
        "total_steps": 2,
        "final_answer": "结果是2",
    }

    def _judge(prompt: str) -> dict:
        score = 3.2 if "类型: action" in prompt else 4.0
        return {
            "role_understanding": "边界用例：低分但高于旧默认阈值",
            "rubrics": [],
            "step_score": score,
            "needs_revision": score < 3.5,
        }

    dag = parse_trajectory(trajectory)
    scorer = ProcessRewardScorer(judge_fn=_judge, min_step_score=3.5)
    report = scorer.score_trajectory(dag, fast_mode=False)

    assert report.per_step[0].step_score == 3.2, "夹具未生效：根因步未被评 3.2"
    assert report.needs_revision is True
    assert report.error_sources == [0], (
        "3.2 < min_step_score(3.5) 的失败步必须能成为根因，"
        f"实际 error_sources={report.error_sources}"
    )

    print("✅ test_error_sources_share_the_revision_threshold passed")


def _threshold_trajectory() -> dict:
    return {
        "session_id": "traj_threshold",
        "query": "计算 1+1",
        "steps": [
            {"step_index": 0, "type": "action",
             "action": {"name": "calculator", "args": {"expression": "1+1"}},
             "content": "calculator"},
            {"step_index": 1, "type": "final", "content": "结果是2"},
        ],
        "total_steps": 2,
        "final_answer": "结果是2",
    }


def test_missing_step_score_is_unscored_not_root_cause():
    """C8 回归：Judge 未给出 step_score → 「未评估」，不是低分根因。

    旧行为回退到中性 3.0，而 3.0 < min_step_score(3.5)，会把未评估的步
    同时标成 needs_revision 和根因。
    """

    def _judge(prompt: str) -> dict:
        if "类型: action" in prompt:
            return {"role_understanding": "", "rubrics": [], "needs_revision": False}
        return {"role_understanding": "", "rubrics": [],
                "step_score": 4.0, "needs_revision": False}

    dag = parse_trajectory(_threshold_trajectory())
    scorer = ProcessRewardScorer(judge_fn=_judge, min_step_score=3.5)
    report = scorer.score_trajectory(dag, fast_mode=False)

    assert report.per_step[0].step_score == 0.0, "未评估不得被当成 3.0 分"
    assert report.per_step[0].needs_revision is True, "评估不完整仍应需要修订"
    assert report.error_sources == [], "未评估的步不得被归因为根因"
    assert report.per_step[1].step_score == 4.0


def test_judge_exception_step_is_unscored_not_root_cause():
    """Judge 调用失败 → 未评估：标 needs_revision，但不是根因。"""

    def _judge(prompt: str) -> dict:
        if "类型: action" in prompt:
            raise RuntimeError("judge boom")
        return {"role_understanding": "", "rubrics": [],
                "step_score": 4.0, "needs_revision": False}

    dag = parse_trajectory(_threshold_trajectory())
    scorer = ProcessRewardScorer(judge_fn=_judge, min_step_score=3.5)
    report = scorer.score_trajectory(dag, fast_mode=False)

    assert report.per_step[0].needs_revision is True
    assert report.error_sources == []


def test_not_applicable_step_is_excluded_from_score_and_revision():
    """方案 C 回归：applicable=False 的步（思考步）不计分、不触发修订、不进总分。"""

    def _judge(prompt: str) -> dict:
        if "类型: action" in prompt:
            return {"role_understanding": "", "rubrics": [],
                    "step_score": 1.0, "needs_revision": True}
        return {"role_understanding": "", "rubrics": [], "applicable": False}

    dag = parse_trajectory(_threshold_trajectory())
    scorer = ProcessRewardScorer(judge_fn=_judge, min_step_score=3.5)
    report = scorer.score_trajectory(dag, fast_mode=False)

    not_applicable = report.per_step[1]
    assert not_applicable.applicable is False
    assert not_applicable.step_score == 0.0
    assert not_applicable.needs_revision is False, "不适用不得触发修订"
    assert report.num_scored == 1, "不适用步不进入已评分集合"
    assert report.overall_score == 1.0, "不适用步不参与加权总分"
    assert report.num_failed_steps == 1
    assert report.error_sources == [0], "低分步仍是根因"


if __name__ == "__main__":
    print("=" * 50)
    print("Process Reward + 错误分析 测试")
    print("=" * 50)
    test_process_reward_good()
    test_iteration_improvement()
    print("\n" + "=" * 50)
    print("✅ 全部测试通过")
    print("=" * 50)
