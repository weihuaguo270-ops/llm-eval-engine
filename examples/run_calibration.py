"""运行 Judge 人机校准并写出报告。

用法：
  # 离线可复现（默认，用数据集内冻结 judge_score）
  python examples/run_calibration.py

  # 在线：对 prompt 调用 JudgeExecutor（需 DEEPSEEK_API_KEY / JUDGE_API_KEY）
  python examples/run_calibration.py --live
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

from eval_engine.judge.calibration import (  # noqa: E402
    JudgeCalibrator,
    format_agreement_markdown,
)


def _live_judge_fn(prompt: str) -> dict:
    from eval_engine.judge.executor import JudgeExecutor

    executor = JudgeExecutor()
    # 简洁强制 JSON 评分，避免依赖外部模板文件路径差异
    full = (
        "请评估下列 Agent 行为描述，只输出 JSON："
        '{"score": <1-5整数>, "rubrics": [{"dimension": "overall", "score": <1-5>, "reason": "..."}]}'
        f"\n\n待评内容：\n{prompt}"
    )
    return executor(full)


def main() -> int:
    parser = argparse.ArgumentParser(description="Judge 人机校准")
    parser.add_argument(
        "--live",
        action="store_true",
        help="调用真实 Judge LLM（需 API Key）",
    )
    parser.add_argument(
        "--data",
        default="",
        help="校准数据 JSON 路径（默认内置 calibration_human_judge.json）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        help="κ 低于该值标记 needs_calibration",
    )
    args = parser.parse_args()

    cal = JudgeCalibrator(threshold=args.threshold)
    if args.data:
        cal.load_golden_file(args.data)
    else:
        cal.load_golden_file()

    if args.live:
        if not (
            os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("JUDGE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        ):
            print("缺少 API Key：请设置 DEEPSEEK_API_KEY / JUDGE_API_KEY")
            return 2
        report = cal.run(judge_fn=_live_judge_fn, mode="live")
    else:
        report = cal.run(mode="offline")

    stamp = datetime.now().strftime("%Y%m%d")
    docs_dir = ROOT / "docs"
    reports_dir = ROOT / "reports"
    docs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    md_path = docs_dir / f"calibration_snapshot_{stamp}.md"
    json_path = reports_dir / f"calibration_report_{stamp}.json"

    title = f"Judge 人机校准快照（{stamp}）"
    md = format_agreement_markdown(report, title=title)
    md += (
        "\n## 如何复现\n\n"
        "```bash\n"
        "python examples/run_calibration.py          # offline\n"
        "python examples/run_calibration.py --live   # 需 API Key\n"
        "```\n\n"
        f"数据文件: `{cal.source_path}`\n"
    )
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(md)
    print(f"\n已写入: {md_path}")
    print(f"已写入: {json_path}")
    return 0 if not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
