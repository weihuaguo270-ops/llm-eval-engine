"""E2E: Episode artifacts → multimodal metrics → release evidence bundle.

Does not require GPU, react-agent, or remote models. Uses precomputed CLIP/safety
fields to prove the multimodal column can evaluate, attach, and block/pass a
cross-agent release decision.

Usage:
  PYTHONPATH=src python examples/e2e_multimodal_release.py
  PYTHONPATH=src python examples/e2e_multimodal_release.py --scenario hold-safety
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.integrations.episode import (
    EvaluationEpisode,
    attach_output_artifacts,
    episode_as_multimodal_case,
    verify_episode_state,
)
from eval_engine.multimodal import (
    ArtifactIntegrityMetric,
    ClipScoreMetric,
    MultimodalEvaluator,
    SafetyClassifierMetric,
    build_multimodal_evidence,
    summarize_case_reports,
)


def _episode(episode_id: str, *, nsfw: float = 0.02) -> EvaluationEpisode:
    episode = EvaluationEpisode(
        episode_id=episode_id,
        task="generate product hero image",
        trajectory={
            "session_id": episode_id,
            "query": "a red ceramic mug on a white table",
            "steps": [{"step": 1, "thought": "emit artifact", "observation": "ok"}],
            "final_answer": "artifact ready",
        },
        framework="format_b",
        agent_version="mm-e2e-v1",
        split="held_out",
        expected_state={"artifact": {"published": True}},
        final_state={"artifact": {"published": True}},
    )
    attach_output_artifacts(
        episode,
        [
            {
                "id": f"{episode_id}-image",
                "media_type": "image",
                "uri": f"artifacts/{episode_id}.png",
                "mime_type": "image/png",
                "width": 512,
                "height": 512,
                "sha256": "a" * 64,
            }
        ],
        prompt="a red ceramic mug on a white table",
        automatic_metrics={"clip_cosine": 0.42, "model": "fixture-clip"},
        safety_result={
            "nsfw_probability": nsfw,
            "passed": nsfw < 0.5,
            "model": "fixture-nsfw",
        },
    )
    return episode


def _sibling_evidence(out: Path) -> dict[str, Path]:
    paths = {
        "process": out / "process_quality.json",
        "failure": out / "failure_gate.json",
        "performance": out / "performance.json",
    }
    paths["process"].write_text(
        json.dumps({"overall_score": 4.1, "source": "e2e-fixture"}, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["failure"].write_text(
        json.dumps({"decision": "pass", "source": "e2e-fixture"}, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["performance"].write_text(
        (ROOT / "examples" / "fixtures" / "performance_pass.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return paths


def run_scenario(scenario: str, work: Path) -> dict:
    nsfw = 0.81 if scenario == "hold-safety" else 0.02
    human_complete = scenario != "review-human"
    episodes_dir = work / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    episodes = [
        _episode("mm-heldout-1", nsfw=nsfw),
        _episode("mm-heldout-2", nsfw=nsfw),
    ]
    evaluator = MultimodalEvaluator(
        [ArtifactIntegrityMetric(), ClipScoreMetric(), SafetyClassifierMetric()]
    )
    reports = []
    for episode in episodes:
        verification = verify_episode_state(episode).to_dict()
        assert verification["passed"] is True
        case = episode_as_multimodal_case(episode)
        report = evaluator.evaluate(case)
        report["split"] = episode.split
        reports.append(report)
        payload = episode.to_dict()
        payload["state_verification"] = verification
        (episodes_dir / f"{episode.episode_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    multimodal = summarize_case_reports(
        reports,
        media_type="image",
        human_review_complete=human_complete if scenario != "review-human" else False,
    )
    # Force the review-human scenario even if auto metrics would otherwise pass.
    if scenario == "review-human":
        multimodal = build_multimodal_evidence(
            media_type="image",
            cases_evaluated=len(reports),
            integrity_passed=True,
            automatic_metrics_complete=True,
            safety_passed=True,
            held_out_included=True,
            human_review_complete=False,
            details={"scenario": scenario},
        )
    multimodal_path = work / "multimodal_evidence.json"
    multimodal_path.write_text(
        json.dumps(multimodal, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    siblings = _sibling_evidence(work)
    release_out = work / "release_decision.json"
    command = [
        sys.executable,
        str(ROOT / "examples" / "run_cross_agent_release.py"),
        str(episodes_dir),
        "--process-quality",
        str(siblings["process"]),
        "--failure-gate",
        str(siblings["failure"]),
        "--performance",
        str(siblings["performance"]),
        "--multimodal-evidence",
        str(multimodal_path),
        "--out",
        str(release_out),
    ]
    import os

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        check=False,
    )
    release = json.loads(release_out.read_text(encoding="utf-8")) if release_out.exists() else {}
    return {
        "scenario": scenario,
        "cli_exit_code": completed.returncode,
        "cli_stdout": completed.stdout,
        "cli_stderr": completed.stderr,
        "multimodal_gate": multimodal.get("gate_decision"),
        "multimodal_passed": multimodal.get("passed"),
        "release_decision": release.get("decision"),
        "hard_failures": release.get("hard_failures"),
        "review_reasons": release.get("review_reasons"),
        "evidence": release.get("evidence"),
        "case_reports": reports,
        "paths": {
            "work": str(work),
            "multimodal": str(multimodal_path),
            "release": str(release_out),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=("pass", "hold-safety", "review-human"),
        default="pass",
    )
    parser.add_argument("--out-dir")
    args = parser.parse_args()

    expected = {
        "pass": ("pass", 0),
        "hold-safety": ("hold", 1),
        "review-human": ("review", 1),
    }[args.scenario]

    if args.out_dir:
        work = Path(args.out_dir)
        work.mkdir(parents=True, exist_ok=True)
        result = run_scenario(args.scenario, work)
    else:
        with tempfile.TemporaryDirectory(prefix="mm-e2e-") as tmp:
            result = run_scenario(args.scenario, Path(tmp))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    decision, exit_code = expected
    ok = (
        result["release_decision"] == decision
        and result["cli_exit_code"] == exit_code
        and result["multimodal_gate"] == decision
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
