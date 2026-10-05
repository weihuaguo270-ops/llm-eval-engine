"""Evaluate exported EvaluationEpisode files and optional sibling evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle
from eval_engine.integrations.episode import import_episode, verify_episode_state


def _load_json(path: str | None) -> dict | None:
    """Load optional evidence while keeping absent evidence explicitly absent."""
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("episodes_dir")
    parser.add_argument("--process-quality")
    parser.add_argument("--failure-gate")
    parser.add_argument("--performance")
    parser.add_argument("--dataset-audit")
    parser.add_argument("--version-comparison")
    parser.add_argument("--human-review")
    parser.add_argument(
        "--verdict-evidence",
        help="决策级结果 JSON（`examples/run_result_evaluation.py` 的产出）",
    )
    parser.add_argument(
        "--max-judge-defect-rate", type=float, default=None,
        help="发布方申报的政策：Judge 缺陷率上限。**不给就等于没有政策 ⇒ 门禁判 review**",
    )
    parser.add_argument(
        "--max-false-pass", type=int, default=None,
        help="发布方申报的政策：漏杀上限（人判缺陷而 Judge 放过）",
    )
    parser.add_argument("--out")
    args = parser.parse_args()

    # Verify each episode before evaluating the bundle so malformed trajectories
    # cannot be mistaken for a passing business result.
    episodes = []
    for path in sorted(Path(args.episodes_dir).glob("*.json")):
        episode = import_episode(json.loads(path.read_text(encoding="utf-8")))
        payload = episode.to_dict()
        payload["state_verification"] = verify_episode_state(episode).to_dict()
        episodes.append(payload)
    # 政策由**发布方**申报；没申报就**不造默认值**（`None` ⇒ 门禁判 review）
    verdict_policy = None
    if args.max_judge_defect_rate is not None:
        verdict_policy = {"max_judge_defect_rate": args.max_judge_defect_rate}
        if args.max_false_pass is not None:
            verdict_policy["max_false_pass"] = args.max_false_pass
    report = evaluate_evidence_bundle(
        episodes=episodes,
        process_quality=_load_json(args.process_quality),
        failure_gate=_load_json(args.failure_gate),
        performance_evidence=_load_json(args.performance),
        dataset_audit=_load_json(args.dataset_audit),
        version_comparison=_load_json(args.version_comparison),
        human_review=_load_json(args.human_review),
        verdict_evidence=_load_json(args.verdict_evidence),
        verdict_policy=verdict_policy,
    )
    # Only an explicit pass is a zero exit code for release automation.
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
