"""eval-engine 快速入门示例"""
import json
from eval_engine.core.contract import VerifierContract
from eval_engine.core.process_reward import ProcessRewardScorer
from eval_engine.core.trajectory_parser import parse_trajectory
from eval_engine.loop.eval_loop import EvalLoopEngine, EvalLoopConfig


def demo_direct_scoring():
    """直接评分示例"""
    trajectory = {
        "session_id": "demo_001",
        "query": "Python 的 sort 函数怎么用？",
        "steps": [
            {"step_index": 0, "type": "thought",
             "content": "用户想知道 Python sort 函数用法"},
            {"step_index": 1, "type": "action",
             "action": {"name": "web_search", "args": {"query": "Python sort"}},
             "content": "web_search(query='Python sort')"},
            {"step_index": 2, "type": "observation",
             "content": "sort() 是列表内置方法，默认升序排序",
             "observation": "sort() 是列表内置方法，默认升序排序"},
            {"step_index": 3, "type": "thought",
             "content": "已获得结果，可以回答"},
            {"step_index": 4, "type": "final",
             "content": "sort() 是 Python 列表的内置方法..."},
        ]
    }

    # 定义评分契约
    contracts = [
        VerifierContract(name="faithfulness",
                         rubric="答案是否基于搜索结果的真实信息",
                         min_score=4, weight=2.0),
        VerifierContract(name="helpfulness",
                         rubric="答案是否清晰解答了用户问题",
                         min_score=3, weight=1.0),
    ]

    # 评分
    dag = parse_trajectory(trajectory)
    scorer = ProcessRewardScorer(judge_fn=lambda p: {
        "score": 4.5,
        "reason": "回答准确且清晰",
        "rubrics": [{"dimension": c.name, "score": 4.0, "reason": "ok"}
                     for c in contracts]
    })
    report = scorer.score_trajectory(dag, fast_mode=True)

    print(f"总分: {report.overall_score:.2f}")
    print(f"步骤数: {report.num_steps}")
    print(f"通过率: {report.pass_rate:.1%}")


if __name__ == "__main__":
    demo_direct_scoring()
