"""Release audit from EvaluationEpisode files.

Reads episodes that may carry step artifacts, scores the trajectory
(parse → multimodal step checks → Process Reward → failure taxonomy),
and prints pass / review / hold. An optional generation-benchmark file
is stored as an appendix and does not affect the decision.

Default scoring reads fixture ``judge_scores``. Pass ``--live`` to score
media steps with ``JudgeExecutor`` (fixture scores are cleared first);
optionally rebuild held-out κ so ``judge_score`` matches this run before
soft scores enter the gate.

When calibration is present, the audit ``calibration`` block matches
``run_calibration.py`` held_out shape (agreement_table + bootstrap CI).
Pass ``--calibration-md`` to write the same markdown snapshot form.

Exit code is 0 only when the decision is pass.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Windows CI may run without PYTHONIOENCODING; keep stdout/stderr UTF-8 capable.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

from eval_engine.core.multimodal_process_judge import (  # noqa: E402
    make_judge_executor_call,
    make_live_dimension_judge,
)
from eval_engine.gates.release_audit import audit_release  # noqa: E402
from eval_engine.judge.calibration import format_agreement_markdown  # noqa: E402
from eval_engine.judge.executor import JudgeExecutor  # noqa: E402

sys.path.insert(0, str(ROOT / "examples"))
from run_calibration import _ensure_judge_env, _load_dotenv  # noqa: E402


def _episode_paths(targets: list[str]) -> list[Path]:
    paths: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            paths.append(path)
        else:
            raise SystemExit(f"episode path not found: {target}")
    if not paths:
        raise SystemExit("no episode json files")
    return paths


def _build_live_judge() -> tuple[object, dict]:
    _load_dotenv()
    wiring = _ensure_judge_env()
    if not (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("JUDGE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    ):
        raise SystemExit(
            "缺少 API Key：请设置 DEEPSEEK_API_KEY / JUDGE_API_KEY（--live 需要真实 Judge）"
        )
    cfg = os.environ.get("JUDGE_LLM_CONFIG") or None
    executor = JudgeExecutor(llm_config_path=cfg)
    executor._resolve()
    llm_call = make_judge_executor_call(executor=executor)
    meta = {
        "mode": "live",
        "model": executor._model or os.environ.get("JUDGE_MODEL") or None,
        "provider": executor.provider_name
        or os.environ.get("JUDGE_PROVIDER")
        or ("deepseek" if "deepseek" in (executor._base_url or "") else None),
        "base_url": executor._base_url or os.environ.get("JUDGE_BASE_URL") or None,
        "scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "wiring": wiring,
    }
    print(
        f"[live] model={meta['model']} base_url={meta['base_url']} "
        f"scored_at={meta['scored_at']} wiring={wiring}",
        file=sys.stderr,
    )
    return (lambda dag: make_live_dimension_judge(dag, llm_call)), meta


def _write_calibration_md(calibration: dict, path: Path, *, mode: str) -> None:
    stamp = datetime.now().strftime("%Y%m%d")
    title = f"多模态过程 held_out 校准快照（{stamp} / {mode}）"
    md = format_agreement_markdown(calibration, title=title)
    unit = calibration.get("kappa_unit") or "dimension_cell"
    md += (
        "\n## κ 单位（钉死）\n\n"
        f"- 主单位: **`{unit}`**（episode × media/final step × dimension）\n"
        f"- episode_count: **{calibration.get('episode_count', '-')}**\n"
        f"- cell sample_size: **{calibration.get('sample_size', '-')}**\n"
        "- 轨迹过程分（min media step）只进发布门禁，**不**作为 κ 聚合单位\n"
        "- 与文本 Judge held_out（n=53 items）分栏；禁止合成总分\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")
    print(f"[cal] wrote {path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "episodes",
        nargs="+",
        help="episode json file(s) or a directory of them",
    )
    parser.add_argument(
        "--generation-appendix",
        help="optional legacy generation-bench json; not used in the decision",
    )
    parser.add_argument("--out", help="write the audit report json here")
    parser.add_argument(
        "--calibration",
        help="held-out human/judge scores; required before process scores gate release",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="score media steps with JudgeExecutor instead of fixture judge_scores",
    )
    parser.add_argument(
        "--rebuild-calibration",
        metavar="PATH",
        help=(
            "after scoring, rewrite held-out judge_score from this run "
            "(keep human_score), write PATH, and gate against it"
        ),
    )
    parser.add_argument(
        "--calibration-md",
        metavar="PATH",
        help="write held_out agreement_table + bootstrap markdown (run_calibration shape)",
    )
    args = parser.parse_args(argv)

    if args.rebuild_calibration and not args.calibration:
        raise SystemExit("--rebuild-calibration requires --calibration with human labels")

    episodes = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in _episode_paths(args.episodes)
    ]
    appendix = None
    if args.generation_appendix:
        appendix = json.loads(Path(args.generation_appendix).read_text(encoding="utf-8"))
    calibration = None
    if args.calibration:
        calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))

    judge_factory = None
    judge_meta = {
        "mode": "fixture",
        "scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    if args.live:
        judge_factory, judge_meta = _build_live_judge()

    report = audit_release(
        episodes,
        judge_factory=judge_factory,
        generation_appendix=appendix,
        calibration=calibration,
        rebuild_calibration=bool(args.rebuild_calibration),
        judge_meta=judge_meta,
    )

    if args.rebuild_calibration and report.get("rebuilt_calibration") is not None:
        Path(args.rebuild_calibration).parent.mkdir(parents=True, exist_ok=True)
        Path(args.rebuild_calibration).write_text(
            json.dumps(report["rebuilt_calibration"], ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"[live] wrote calibration {args.rebuild_calibration}", file=sys.stderr)

    cal = report.get("calibration")
    if args.calibration_md and cal:
        _write_calibration_md(cal, Path(args.calibration_md), mode=judge_meta.get("mode") or "fixture")

    if cal and cal.get("sample_size"):
        boot = (cal.get("bootstrap") or {}).get("kappa") or {}
        print(
            f"summary: kappa_unit={cal.get('kappa_unit')} "
            f"n_cells={cal.get('sample_size')} episodes={cal.get('episode_count')} "
            f"kappa={cal.get('kappa')} "
            f"ci=[{boot.get('low')}, {boot.get('high')}] "
            f"needs_calibration={cal.get('needs_calibration')}",
            file=sys.stderr,
        )

    printable = dict(report)
    printable.pop("rebuilt_calibration", None)
    rendered = json.dumps(printable, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
