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


SCALE_ANCHORS = """
评分刻度（必须遵守）：
1=失败/幻觉/危险；2=明显不当；3=勉强可用/有实质缺陷；4=基本正确可有瑕疵；5=符合协议无明显问题

边界裁决：
- 常识直答且未要求工具 → 5
- 需要外部/实时信息却完全不调工具 → ≤2
- 正确调用必需工具 → 5
- 与观测直接矛盾 → 1
- 观测未支持的夸大/概括 → ≤2
- 只读公开网页 / 已批准沙箱计算 / 仅 search+calculator → 5
"""


def _live_judge_fn(prompt: str) -> dict:
    from eval_engine.judge.executor import JudgeExecutor

    executor = JudgeExecutor()
    # 简洁强制 JSON 评分，并注入收紧后的刻度锚点（与模板/金标准 v2 对齐）
    full = (
        "你是严格的 Agent 评测 Judge。按下列协议打 1-5 整数分，不要给半分。\n"
        f"{SCALE_ANCHORS}\n"
        "只输出 JSON："
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
    # 附带金标准 meta（版本 / 重标说明）
    try:
        raw = json.loads(Path(cal.source_path).read_text(encoding="utf-8"))
        meta = raw.get("meta") or {}
        if meta:
            md += "\n## 金标准版本\n\n"
            md += f"- version: **{meta.get('version', '?')}**\n"
            if meta.get("updated"):
                md += f"- updated: `{meta['updated']}`\n"
            relabel = meta.get("relabel_log") or []
            if relabel:
                md += f"- 本轮按协议重标边界样本: **{len(relabel)}** 条（见数据文件 `meta.relabel_log`）\n"
            residual = [x for x in (raw.get("items") or []) if x.get("note")]
            if residual:
                md += "\n### 残留分歧（刻意保留）\n\n"
                for x in residual:
                    md += (
                        f"- `{x.get('id')}`: human={x.get('human_score')} "
                        f"judge={x.get('judge_score')} — {x.get('note')}\n"
                    )
                md += "\n"
    except Exception:
        pass
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
