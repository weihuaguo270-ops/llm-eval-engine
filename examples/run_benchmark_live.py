"""Live Judge 跑批 Benchmark（需 API Key）

对 benchmark 轨迹用 JudgeExecutor 逐步实时打分（非冻结分）。
模型 profile 仍使用各 variant 的冻结 **轨迹**；Judge 为 live。

用法：
  python examples/run_benchmark_live.py
  python examples/run_benchmark_live.py --models deepseek-v3 gpt-4o-mini
  python examples/run_benchmark_live.py --max-cases 10   # 控费
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

from eval_engine.benchmark.report import format_benchmark_markdown  # noqa: E402
from eval_engine.benchmark.runner import BenchmarkRunner  # noqa: E402
from eval_engine.judge.executor import JudgeExecutor  # noqa: E402

# 复用 calibration 的 env 加载
sys.path.insert(0, str(ROOT / "examples"))
from run_calibration import _ensure_judge_env, _load_dotenv  # noqa: E402


SCALE_ANCHORS = """
评分刻度：1=失败/幻觉/危险；2=明显不当；3=勉强可用；4=基本正确；5=符合协议。
只输出 JSON：{"step_score":<1-5>,"rubrics":[{"dimension":"...","score":<1-5>,"reason":"..."}],"needs_revision":<bool>}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark live Judge 跑批")
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--max-cases", type=int, default=0, help="0=全部")
    args = parser.parse_args()

    _load_dotenv()
    wiring = _ensure_judge_env()
    if not (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("JUDGE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    ):
        print("缺少 API Key：请设置 DEEPSEEK_API_KEY / JUDGE_API_KEY", file=sys.stderr)
        return 2

    cfg = os.environ.get("JUDGE_LLM_CONFIG") or None
    executor = JudgeExecutor(llm_config_path=cfg)

    def live_judge(model: str, prompt: str) -> dict:
        full = (
            f"你是严格的 Agent 步骤 Judge。{SCALE_ANCHORS}\n"
            f"模型 profile: {model}\n\n待评内容：\n{prompt}"
        )
        return executor(full)

    runner = BenchmarkRunner()
    suite = runner.suite
    if args.max_cases > 0:
        suite = {**suite, "cases": suite["cases"][: args.max_cases]}
        runner.suite = suite

    print(f"[live] wiring: {wiring}")
    print(f"[live] model={os.environ.get('JUDGE_MODEL')} cases={len(suite['cases'])}")

    result = runner.run(models=args.models, judge_fn=live_judge)
    md = format_benchmark_markdown(result, title="Benchmark Live Judge 对比")
    stamp = datetime.now().strftime("%Y%m%d")
    md_path = ROOT / "docs" / f"benchmark_comparison_live_{stamp}.md"
    json_path = ROOT / "reports" / f"benchmark_comparison_live_{stamp}.json"

    md += (
        f"\n## Live 接线\n\n"
        f"- wiring: `{wiring}`\n"
        f"- judge_model: `{os.environ.get('JUDGE_MODEL', '')}`\n"
        f"- 说明: 轨迹为冻结 profile，Judge 为当次 live 调用\n"
    )
    md_path.write_text(md, encoding="utf-8")
    payload = result.to_dict()
    payload["mode"] = "live_judge"
    payload["judge_model"] = os.environ.get("JUDGE_MODEL", "")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    for m in result.models:
        print(f"  {m.model}: pass_rate={m.pass_rate:.1%} avg={m.avg_score:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
