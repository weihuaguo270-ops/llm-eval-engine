"""端到端：轨迹 JSON → Process Reward 评分 → 文本报告

模拟 react-agent Harness 产出 trajectory 后交给 eval-engine 的完整路径。
不依赖 react-agent 安装；使用 benchmark 内一条样本轨迹。

用法：
  python examples/e2e_trajectory_eval.py
  python examples/e2e_trajectory_eval.py --case bench_tool_001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.benchmark.runner import load_benchmark_suite
from eval_engine.core.process_reward import (
    ProcessRewardScorer,
    analyze_error_propagation,
    pack_revision_instructions,
)
from eval_engine.core.trajectory_parser import parse_trajectory
from eval_engine.observability.report import format_report
from eval_engine.loop.eval_loop import EvalLoopResult


def _frozen_judge(variant: dict):
    outputs = variant.get("step_judge_outputs") or []
    idx = {"n": 0}

    def judge_fn(prompt: str) -> dict:
        i = idx["n"]
        idx["n"] += 1
        return outputs[i] if i < len(outputs) else {"step_score": 3.0, "rubrics": []}

    return judge_fn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="bench_tool_001")
    parser.add_argument("--model", default="deepseek-v3")
    args = parser.parse_args()

    suite = load_benchmark_suite()
    case = next((c for c in suite["cases"] if c["id"] == args.case), None)
    if not case:
        print(f"case not found: {args.case}", file=sys.stderr)
        return 1

    variant = case["variants"][args.model]
    trajectory = variant["trajectory"]
    traj_path = ROOT / "reports" / f"e2e_{args.case}_trajectory.json"
    traj_path.parent.mkdir(exist_ok=True)
    traj_path.write_text(json.dumps(trajectory, ensure_ascii=False, indent=2), encoding="utf-8")

    dag = parse_trajectory(trajectory)
    scorer = ProcessRewardScorer(judge_fn=_frozen_judge(variant))
    report = scorer.score_trajectory(dag, fast_mode=False)
    err = analyze_error_propagation(report, dag)

    loop_result = EvalLoopResult(
        query=case["query"],
        task_type="generative_task",
        final_output=trajectory.get("final_answer", ""),
        report=report,
        iterations=1,
        healing_log=[{
            "iteration": 1,
            "overall_score": report.overall_score,
            "needs_revision": report.needs_revision,
            "num_failed_steps": report.num_failed_steps,
        }],
        error_analysis=err,
        passed=not report.needs_revision,
    )

    text = format_report(loop_result, detailed=True)
    out_md = ROOT / "docs" / f"e2e_report_{args.case}.md"
    out_md.write_text(text, encoding="utf-8")

    print(f"[e2e] trajectory: {traj_path}")
    print(f"[e2e] report: {out_md}")
    print(f"[e2e] score={report.overall_score:.2f} passed={loop_result.passed}")
    if report.needs_revision:
        fix = pack_revision_instructions(report, dag)
        print(f"[e2e] revision preview:\n{fix[:400]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
