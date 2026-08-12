"""Evaluate exported EvaluationEpisode files and optional sibling evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle
from eval_engine.integrations.episode import import_episode, verify_episode_state


def _load_json(path: str | None) -> dict | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("episodes_dir")
    parser.add_argument("--process-quality")
    parser.add_argument("--failure-gate")
    parser.add_argument("--performance")
    parser.add_argument("--out")
    args = parser.parse_args()

    episodes = []
    for path in sorted(Path(args.episodes_dir).glob("*.json")):
        episode = import_episode(json.loads(path.read_text(encoding="utf-8")))
        payload = episode.to_dict()
        payload["state_verification"] = verify_episode_state(episode).to_dict()
        episodes.append(payload)
    report = evaluate_evidence_bundle(
        episodes=episodes,
        process_quality=_load_json(args.process_quality),
        failure_gate=_load_json(args.failure_gate),
        performance_evidence=_load_json(args.performance),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
