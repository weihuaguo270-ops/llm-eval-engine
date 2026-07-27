"""Agent 驱动的 Benchmark：react-agent 产轨迹 → eval-engine Process Reward 评分

用法：
  # mock harness（无需 API，验证 react-agent 集成）
  python examples/run_benchmark_agent.py --mode mock --max-cases 5

  # live Agent（需 DEEPSEEK_API_KEY / OPENAI_API_KEY）
  python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3
  python examples/run_benchmark_agent.py --mode agent --providers deepseek-v3 gpt-4o-mini

  # 无 Key 时自动 fallback 到 suite 内冻结轨迹
  python examples/run_benchmark_agent.py --mode agent --fallback-frozen
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from run_calibration import _load_dotenv, _ensure_judge_env  # noqa: E402

_load_dotenv()
_ensure_judge_env()

from eval_engine.benchmark.report import format_benchmark_markdown  # noqa: E402
from eval_engine.benchmark.runner import (  # noqa: E402
    BenchmarkRunner,
    CaseResult,
    ModelRunResult,
    BenchmarkRunResult,
)
from eval_engine.core.process_reward import (  # noqa: E402
    ProcessRewardScorer,
    analyze_error_propagation,
)
from eval_engine.core.trajectory_parser import parse_trajectory  # noqa: E402
from eval_engine.core.failure_taxonomy import summarize_failures  # noqa: E402
from eval_engine.integrations.react_agent import (  # noqa: E402
    find_react_agent_root,
    provider_for_profile,
    run_benchmark_query,
)


def _mock_judge(prompt: str) -> dict:
    score = 4.0
    if "mock observation" in prompt.lower():
        score = 3.8
    return {
        "role_understanding": "benchmark agent judge",
        "rubrics": [{"dimension": "general", "score": score, "reason": "agent run"}],
        "step_score": score,
        "needs_revision": score < 3.5,
    }


def _live_judge_factory():
    from eval_engine.judge.executor import JudgeExecutor

    executor = JudgeExecutor(
        llm_config_path=os.environ.get("JUDGE_LLM_CONFIG") or None,
    )

    def judge(prompt: str) -> dict:
        full = (
            "你是 Agent 步骤 Judge。按 1-5 打分，只输出 JSON："
            '{"step_score":n,"rubrics":[{"dimension":"...","score":n,"reason":"..."}],'
            '"needs_revision":bool}\n\n'
            f"{prompt}"
        )
        return executor(full)

    return judge


def _load_judge_env(react_root: Path | None) -> None:
    if react_root and (react_root / "llm_config.json").is_file():
        os.environ.setdefault("JUDGE_LLM_CONFIG", str(react_root / "llm_config.json"))
    if os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("JUDGE_API_KEY"):
        os.environ["JUDGE_API_KEY"] = os.environ["DEEPSEEK_API_KEY"]


def run_agent_benchmark(
    *,
    mode: str,
    profiles: list[str],
    max_cases: int,
    judge_mode: str,
    react_root: Path,
    min_step_score: float,
    fallback_frozen: bool,
    timeout: int,
) -> BenchmarkRunResult:
    runner = BenchmarkRunner()
    cases = runner.suite["cases"]
    if max_cases > 0:
        cases = cases[:max_cases]

    judge_fn = _mock_judge
    if judge_mode == "live":
        _load_judge_env(react_root)
        if os.environ.get("JUDGE_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"):
            judge_fn = _live_judge_factory()
        else:
            print("[warn] live judge requested but no API key; using mock judge")

    model_results: list[ModelRunResult] = []
    taxonomy_inputs: list[tuple[str, str, Any]] = []

    for profile in profiles:
        mr = ModelRunResult(model=profile)
        for case in cases:
            query = case["query"]
            variant = (case.get("variants") or {}).get(profile) or {}
            frozen_traj = variant.get("trajectory")

            agent_res = run_benchmark_query(
                query,
                profile,
                mode=mode,
                react_root=react_root,
                timeout=timeout,
                frozen_trajectory=frozen_traj,
            )

            if agent_res.trajectory is None and fallback_frozen and frozen_traj:
                agent_res = run_benchmark_query(
                    query,
                    profile,
                    mode="frozen",
                    react_root=react_root,
                    frozen_trajectory=frozen_traj,
                )

            if agent_res.trajectory is None:
                print(f"[skip] {case['id']} profile={profile}: {agent_res.error}")
                continue

            dag = parse_trajectory(agent_res.trajectory)
            scorer = ProcessRewardScorer(judge_fn=judge_fn, min_step_score=min_step_score)
            report = scorer.score_trajectory(dag, fast_mode=False)
            err = analyze_error_propagation(report, dag)
            passed = not report.needs_revision and report.overall_score >= min_step_score

            cr = CaseResult(
                case_id=case["id"],
                category=case.get("category", "unknown"),
                query=query,
                passed=passed,
                overall_score=report.overall_score,
                pass_rate=report.pass_rate,
                num_failed_steps=report.num_failed_steps,
                error_sources=report.error_sources,
                latency_ms=agent_res.duration_ms or variant.get("latency_ms", 0),
                tokens=variant.get("tokens", 0),
                report=report,
                error_analysis=err,
            )
            mr.cases.append(cr)
            if not passed:
                taxonomy_inputs.append((case["id"], case.get("category", "unknown"), report))
            print(
                f"  [{profile}] {case['id']} mode={agent_res.mode} "
                f"score={report.overall_score:.2f} pass={passed}"
            )
        model_results.append(mr)

    import time

    taxonomy = summarize_failures(taxonomy_inputs).to_dict()
    return BenchmarkRunResult(
        suite_version=int(runner.suite.get("meta", {}).get("version", 2)),
        models=model_results,
        taxonomy=taxonomy,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="react-agent 驱动 Benchmark")
    parser.add_argument(
        "--mode",
        choices=["mock", "agent", "frozen"],
        default="mock",
        help="mock=harness无LLM; agent=react_loop子进程; frozen=只用suite轨迹",
    )
    parser.add_argument(
        "--providers",
        nargs="*",
        default=["deepseek-v3"],
        help="benchmark profile 名（默认 deepseek-v3）",
    )
    parser.add_argument("--max-cases", type=int, default=0, help="0=全部 32 条")
    parser.add_argument("--judge", choices=["mock", "live"], default="mock")
    parser.add_argument("--react-agent-root", default="", help="react-agent 路径")
    parser.add_argument(
        "--fallback-frozen",
        action="store_true",
        help="agent 失败或无 Key 时回退冻结轨迹",
    )
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--compare-offline", action="store_true", help="打印与 offline suite 差异摘要")
    args = parser.parse_args()

    react_root = find_react_agent_root(args.react_agent_root or None)
    if react_root is None:
        print(
            "ERROR: 未找到 react-agent。请 clone 到 ../react-agent 或设置 REACT_AGENT_ROOT",
            file=sys.stderr,
        )
        return 2
    print(f"react-agent: {react_root}")

    if args.mode == "agent":
        for p in args.providers:
            prov = provider_for_profile(p)
            print(f"  profile {p} -> LLM_PROVIDER={prov}")

    result = run_agent_benchmark(
        mode=args.mode,
        profiles=args.providers,
        max_cases=args.max_cases,
        judge_mode=args.judge,
        react_root=react_root,
        min_step_score=3.5,
        fallback_frozen=args.fallback_frozen,
        timeout=args.timeout,
    )

    title = f"Benchmark Agent 跑批（mode={args.mode}, judge={args.judge}）"
    md = format_benchmark_markdown(result, title=title)
    md += f"\n## Agent 集成\n\n- react-agent: `{react_root}`\n- mode: `{args.mode}`\n"
    stamp = datetime.now().strftime("%Y%m%d")
    tag = f"agent_{args.mode}" if args.mode != "agent" else "live_agent"
    md_path = ROOT / "docs" / f"benchmark_comparison_{tag}_{stamp}.md"
    json_path = ROOT / "reports" / f"benchmark_comparison_{tag}_{stamp}.json"
    md_path.write_text(md, encoding="utf-8")
    payload = result.to_dict()
    payload["agent_mode"] = args.mode
    payload["judge_mode"] = args.judge
    payload["react_agent_root"] = str(react_root)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nWrote {md_path}")
    print(f"Wrote {json_path}")
    for m in result.models:
        print(f"  {m.model}: pass={m.pass_rate:.1%} avg={m.avg_score:.2f} n={m.num_cases}")

    if args.compare_offline and args.mode != "frozen":
        offline = BenchmarkRunner().run(models=args.providers)
        print("\n--- vs offline frozen suite ---")
        for om in offline.models:
            am = next((x for x in result.models if x.model == om.model), None)
            if am:
                print(
                    f"  {om.model}: agent_pass={am.pass_rate:.1%} offline_pass={om.pass_rate:.1%} "
                    f"agent_avg={am.avg_score:.2f} offline_avg={om.avg_score:.2f}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
