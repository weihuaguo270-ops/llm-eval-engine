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


def _load_dotenv() -> None:
    """加载本地 / 姊妹仓 .env，不打印任何密钥值。"""
    candidates = [
        ROOT / ".env",
        Path.cwd() / ".env",
        ROOT.parent / "react-agent" / ".env",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, val = s.partition("=")
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val
        return


def _ensure_judge_env() -> str:
    """把常见 Agent Key 映射到 JudgeExecutor 所需环境变量。返回解析说明（无密钥）。"""
    notes: list[str] = []
    if os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("JUDGE_API_KEY"):
        os.environ["JUDGE_API_KEY"] = os.environ["DEEPSEEK_API_KEY"]
        notes.append("JUDGE_API_KEY<-DEEPSEEK_API_KEY")
    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("JUDGE_API_KEY"):
        os.environ["JUDGE_API_KEY"] = os.environ["OPENAI_API_KEY"]
        notes.append("JUDGE_API_KEY<-OPENAI_API_KEY")

    if os.environ.get("JUDGE_API_KEY") and not os.environ.get("JUDGE_BASE_URL"):
        # DeepSeek 默认；若用户显式设了 OPENAI 且无 DEEPSEEK，用 OpenAI
        if os.environ.get("DEEPSEEK_API_KEY"):
            os.environ["JUDGE_BASE_URL"] = "https://api.deepseek.com"
            os.environ.setdefault("JUDGE_MODEL", "deepseek-chat")
            notes.append("JUDGE_BASE_URL=deepseek")
        else:
            os.environ["JUDGE_BASE_URL"] = "https://api.openai.com/v1"
            os.environ.setdefault("JUDGE_MODEL", "gpt-4o-mini")
            notes.append("JUDGE_BASE_URL=openai")

    cfg = ROOT.parent / "react-agent" / "llm_config.json"
    if cfg.is_file() and not os.environ.get("JUDGE_LLM_CONFIG"):
        os.environ["JUDGE_LLM_CONFIG"] = str(cfg)
        notes.append("JUDGE_LLM_CONFIG=react-agent")

    return ", ".join(notes) or "env-as-is"


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

    cfg = os.environ.get("JUDGE_LLM_CONFIG") or None
    executor = JudgeExecutor(llm_config_path=cfg)
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
    _load_dotenv()
    wiring = _ensure_judge_env()

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
        print(f"[live] judge wiring: {wiring}")
        print(f"[live] model={os.environ.get('JUDGE_MODEL')} base={os.environ.get('JUDGE_BASE_URL')}")
        report = cal.run(judge_fn=_live_judge_fn, mode="live")
        # 全 3 分几乎一定是 fallback（未真正打到模型）
        scores = [p.get("judge") for p in (report.get("pairs") or [])]
        if scores and len(set(scores)) == 1 and scores[0] == 3:
            print(
                "[error] live 结果疑似 Judge fallback（全为 3 分），未写入快照。"
                "请检查 JUDGE_BASE_URL / JUDGE_API_KEY / 网络。",
                file=sys.stderr,
            )
            return 3
    else:
        report = cal.run(mode="offline")

    stamp = datetime.now().strftime("%Y%m%d")
    mode_tag = "live" if args.live else "offline"
    stem = f"calibration_snapshot_{stamp}_{mode_tag}"
    docs_dir = ROOT / "docs"
    reports_dir = ROOT / "reports"
    docs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    md_path = docs_dir / f"{stem}.md"
    json_path = reports_dir / f"calibration_report_{stamp}_{mode_tag}.json"

    # 兼容旧路径：offline 额外写一份无后缀的主快照
    legacy_md = docs_dir / f"calibration_snapshot_{stamp}.md"
    legacy_json = reports_dir / f"calibration_report_{stamp}.json"

    title = f"Judge 人机校准快照（{stamp} / {mode_tag}）"
    md = format_agreement_markdown(report, title=title)
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
                md += "\n### 金标准内残留分歧（offline 冻结分，非本轮 live）\n\n"
                for x in residual:
                    md += (
                        f"- `{x.get('id')}`: human={x.get('human_score')} "
                        f"frozen_judge={x.get('judge_score')} — {x.get('note')}\n"
                    )
                md += "\n"
    except Exception:
        pass
    if args.live:
        md += (
            f"\n## Live 接线\n\n"
            f"- wiring: `{wiring}`\n"
            f"- model: `{os.environ.get('JUDGE_MODEL', '')}`\n"
            f"- base_url: `{os.environ.get('JUDGE_BASE_URL', '')}`\n"
        )
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
    if not args.live:
        legacy_md.write_text(md, encoding="utf-8")
        legacy_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(md)
    print(f"\n已写入: {md_path}")
    print(f"已写入: {json_path}")
    return 0 if not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
