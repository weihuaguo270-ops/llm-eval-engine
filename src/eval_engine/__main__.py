"""eval-engine CLI — 命令行评估工具

Usage:
    python -m eval_engine eval --query "xxx" --trajectory trajectory.json
    python -m eval_engine report --file result.json
"""

from __future__ import annotations
import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="LLM Eval Engine CLI")
    sub = parser.add_subparsers(dest="command")

    # eval command
    eval_cmd = sub.add_parser("eval", help="评估 Agent 执行轨迹")
    eval_cmd.add_argument("--query", required=True, help="用户原始输入")
    eval_cmd.add_argument("--trajectory", required=True, help="轨迹 JSON 文件路径")
    eval_cmd.add_argument("--verbose", action="store_true", help="详细输出")

    # report command
    report_cmd = sub.add_parser("report", help="查看评估报告")
    report_cmd.add_argument("--file", required=True, help="评估结果 JSON 文件")

    # version
    sub.add_parser("version", help="显示版本信息")

    args = parser.parse_args()

    if args.command == "version":
        from eval_engine import __version__
        print(f"eval-engine v{__version__}")
    elif args.command == "eval":
        _run_eval(args)
    elif args.command == "report":
        _show_report(args)
    else:
        parser.print_help()


def _run_eval(args):
    """运行评估"""
    from eval_engine.core.trajectory_parser import parse_trajectory
    from eval_engine.core.process_reward import ProcessRewardScorer

    with open(args.trajectory, "r") as f:
        trajectory = json.load(f)

    if args.verbose:
        print(f"📥 加载轨迹: {args.trajectory}")
        print(f"💬 查询: {args.query[:80]}...")

    dag = parse_trajectory(trajectory)

    # Simple judge function for demo
    def demo_judge(prompt: str) -> dict:
        return {"score": 4.0, "reason": "评分完成", "details": []}

    scorer = ProcessRewardScorer(judge_fn=demo_judge)
    report = scorer.score_trajectory(dag, fast_mode=True)

    print(f"\n📊 评估结果")
    print(f"{'='*40}")
    print(f"  总分: {report.overall_score:.2f}")
    print(f"  步骤数: {report.num_steps}")
    print(f"  通过率: {report.pass_rate:.1%}")
    print(f"  需修正: {'是' if report.needs_revision else '否'}")
    print()


def _show_report(args):
    """显示评估报告"""
    with open(args.file, "r") as f:
        data = json.load(f)
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
