"""运行固定 Benchmark 任务集，输出多模型对比报告。

用法：
  python examples/run_benchmark.py
  python examples/run_benchmark.py --models deepseek-v3 gpt-4o-mini
  python examples/run_benchmark.py --save-baseline
  python examples/run_benchmark.py --compare
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.benchmark.report import comparison_table, format_benchmark_markdown  # noqa: E402
from eval_engine.benchmark.runner import BenchmarkRunner  # noqa: E402
from eval_engine.gates.baseline import BaselineManager, shipped_baseline_path  # noqa: E402
from eval_engine.gates.regression_gate import RegressionGate  # noqa: E402


def result_to_gate_report(result) -> dict:
    """把 benchmark 结果转为 regression gate 可对比的结构。"""
    # 用全模型平均作为门禁分数（也可改为 best model）
    if not result.models:
        return {"overall_score": 0, "summary": {"pass_rate": 0}, "by_category": {}}
    avg_score = sum(m.avg_score for m in result.models) / len(result.models)
    avg_pass = sum(m.pass_rate for m in result.models) / len(result.models)
    by_cat: dict[str, dict] = {}
    categories = {c.category for m in result.models for c in m.cases}
    for cat in categories:
        scores = []
        passes = []
        for m in result.models:
            group = [c for c in m.cases if c.category == cat]
            if group:
                scores.append(sum(c.overall_score for c in group) / len(group))
                passes.append(sum(1 for c in group if c.passed) / len(group))
        by_cat[cat] = {
            "overall_score": round(sum(scores) / len(scores), 3) if scores else 0,
            "pass_rate": round(sum(passes) / len(passes), 4) if passes else 0,
            "num_cases": len([c for c in result.models[0].cases if c.category == cat]),
        }
    return {
        "overall_score": round(avg_score, 3),
        "summary": {
            "pass_rate": round(avg_pass, 4),
            "num_cases": result.models[0].num_cases if result.models else 0,
            "num_failed_cases": sum(
                m.num_cases - m.pass_count for m in result.models
            ),
            "num_failed_steps": sum(
                c.num_failed_steps for m in result.models for c in m.cases
            ),
        },
        "by_category": by_cat,
        "benchmark": comparison_table(result),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark 多模型跑批")
    parser.add_argument("--models", nargs="*", default=None, help="指定模型 profile")
    parser.add_argument("--suite", default="", help="benchmark_suite.json 路径")
    parser.add_argument("--save-baseline", action="store_true", help="保存当前结果为 baseline")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="与 shipped/user baseline 对比并跑回归门禁",
    )
    parser.add_argument(
        "--baseline-dir",
        default="",
        help="baseline 目录（默认用户态 + shipped 回退）",
    )
    args = parser.parse_args()

    runner = BenchmarkRunner(suite_path=args.suite or None)
    result = runner.run(models=args.models)
    md = format_benchmark_markdown(result)
    stamp = datetime.now().strftime("%Y%m%d")
    docs_dir = ROOT / "docs"
    reports_dir = ROOT / "reports"
    docs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    md_path = docs_dir / f"benchmark_comparison_{stamp}.md"
    json_path = reports_dir / f"benchmark_comparison_{stamp}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Benchmark done: {result.models[0].num_cases} cases x {len(result.models)} models")
    for m in result.models:
        print(f"  {m.model}: pass={m.pass_rate:.1%} avg={m.avg_score:.2f}")
    print(f"\n已写入: {md_path}")
    print(f"已写入: {json_path}")

    gate_report = result_to_gate_report(result)
    bm = BaselineManager(baseline_dir=args.baseline_dir or None)

    if args.save_baseline:
        path = bm.save(gate_report)
        print(f"已保存 baseline: {path}")

    if args.compare:
        shipped = shipped_baseline_path()
        if shipped.is_file():
            print(f"\n[compare] shipped baseline: {shipped}")
        gate = RegressionGate(bm)
        eval_result = gate.evaluate(gate_report)
        print(eval_result["message"])
        if eval_result.get("reasons"):
            for r in eval_result["reasons"]:
                print(f"  - {r}")
        return 0 if eval_result["passed"] else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
