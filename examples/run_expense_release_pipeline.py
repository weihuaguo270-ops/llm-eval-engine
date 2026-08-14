"""Run the expense Agent release exercise across the portfolio repositories."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval_engine.dataset.governance import audit_splits, build_manifest
from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle
from eval_engine.integrations.episode import import_episode, verify_episode_state


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("PORTFOLIO_WORKSPACE", ROOT.parent)).resolve()
REACT_EXPORTER = WORKSPACE / "react-agent" / "examples" / "eval" / "run_expense_business_eval.py"
DEFAULT_PERFORMANCE = WORKSPACE / "gpu-evidence" / "agent_release_performance_20260812.json"
DEFAULT_HUMAN_REVIEW = Path(__file__).with_name("fixtures") / "expense_human_review.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _export_run(
    target: Path,
    *,
    version: str,
    profile: str,
) -> dict[str, Any]:
    episodes = target / "episodes"
    report = target / "business_report.json"
    command = [
        sys.executable,
        str(REACT_EXPORTER),
        "--agent-version",
        version,
        "--profile",
        profile,
        "--episodes-out",
        str(episodes),
        "--report-out",
        str(report),
    ]
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if not report.exists():
        raise RuntimeError(completed.stderr or completed.stdout or "expense export failed")
    payload = _read_json(report)
    payload["exit_code"] = completed.returncode
    return payload


def _load_episodes(directory: Path) -> list[dict[str, Any]]:
    episodes = []
    for path in sorted(directory.glob("*.json")):
        episode = import_episode(_read_json(path))
        payload = episode.to_dict()
        payload["state_verification"] = verify_episode_state(episode).to_dict()
        episodes.append(payload)
    return episodes


def _dataset_evidence(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    cases = [
        {
            "id": item["episode_id"],
            "split": item["split"],
            "task": item["task"],
            "expected_state": item["expected_state"],
        }
        for item in episodes
    ]
    manifest = build_manifest(
        "expense-business-cases",
        "v1",
        cases,
        source="react-agent business_cases.json",
    )
    audit = audit_splits(cases, required_splits=("dev", "golden", "held_out"))
    audit["fingerprint"] = manifest.fingerprint
    audit["manifest"] = manifest.to_dict()
    return audit


def _compare_versions(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
) -> dict[str, Any]:
    old = {item["episode_id"]: item for item in baseline}
    new = {item["episode_id"]: item for item in candidate}
    comparable = sorted(set(old) & set(new))
    regressions = [
        case_id
        for case_id in comparable
        if old[case_id]["state_verification"]["passed"]
        and not new[case_id]["state_verification"]["passed"]
    ]
    return {
        "baseline_version": baseline[0]["agent_version"] if baseline else "",
        "candidate_version": candidate[0]["agent_version"] if candidate else "",
        "comparable_cases": len(comparable),
        "regressions": regressions,
        "decision": "hold" if regressions else "pass",
    }


def _process_quality(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    scores = []
    rows = []
    for episode in episodes:
        tools = [
            step.get("action", {}).get("name")
            for step in episode["trajectory"].get("steps", [])
            if isinstance(step.get("action"), dict)
        ]
        state_ok = episode["state_verification"]["passed"] is True
        score = 5.0 if state_ok and tools == ["inspect_expense_claim", "decide_expense_claim"] else 1.0
        scores.append(score)
        rows.append({"case_id": episode["episode_id"], "score": score, "tools": tools})
    return {
        "metric": "deterministic_expense_process_rubric/v1",
        "overall_score": sum(scores) / len(scores) if scores else 0.0,
        "cases": rows,
    }


def _human_review(path: Path) -> dict[str, Any]:
    source = _read_json(path)
    reviews = list(source.get("reviews") or [])
    return {
        "review_batch": source.get("review_batch"),
        "required_cases": int(source.get("required_cases") or 0),
        "reviewed_cases": len(reviews),
        "approved_case_ids": [row["case_id"] for row in reviews if row.get("approved") is True],
        "rejected_case_ids": [row["case_id"] for row in reviews if row.get("approved") is not True],
        "evidence_boundary": source.get("evidence_boundary"),
    }


def _failure_snapshot(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        from trace_debugger import analyze_trajectory_dict, analysis_to_dict
    except ImportError as exc:
        raise RuntimeError("trace-debugger must be installed for the portfolio release pipeline") from exc

    rows = []
    distribution: Counter[str] = Counter()
    for episode in episodes:
        analysis = analysis_to_dict(analyze_trajectory_dict(episode["trajectory"]))
        failures = sorted(
            {
                failure
                for path in analysis["paths"]
                for failure in path.get("failures") or []
            }
        )
        distribution.update(failures)
        rows.append(
            {
                "session_id": episode["episode_id"],
                "failure_types": failures,
                "needs_fix": analysis["needs_fix"],
            }
        )
    return {
        "n_trajectories": len(rows),
        "distribution": dict(sorted(distribution.items())),
        "trajectories": rows,
    }


def _feedback_queue(
    candidate: list[dict[str, Any]],
    version_comparison: dict[str, Any],
    failure_snapshot: dict[str, Any],
    human_review: dict[str, Any],
) -> list[dict[str, Any]]:
    reasons: dict[str, set[str]] = {}
    for case_id in version_comparison["regressions"]:
        reasons.setdefault(case_id, set()).add("business_state_regression")
    for row in failure_snapshot["trajectories"]:
        for failure in row["failure_types"]:
            reasons.setdefault(row["session_id"], set()).add(f"trajectory:{failure}")
    for case_id in human_review["rejected_case_ids"]:
        reasons.setdefault(case_id, set()).add("human_review_rejected")

    by_id = {item["episode_id"]: item for item in candidate}
    return [
        {
            "case_id": case_id,
            "split": by_id.get(case_id, {}).get("split", "unknown"),
            "reasons": sorted(items),
            "action": "triage_then_promote_to_golden_after_fix",
            "status": "pending",
        }
        for case_id, items in sorted(reasons.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/expense-release/latest")
    parser.add_argument("--candidate-version", default="expense-agent-v2")
    parser.add_argument("--candidate-profile", choices=("reference", "no_action"), default="reference")
    parser.add_argument("--human-review", type=Path, default=DEFAULT_HUMAN_REVIEW)
    parser.add_argument("--performance", type=Path, default=DEFAULT_PERFORMANCE)
    args = parser.parse_args()

    output = Path(args.out).resolve()
    baseline_report = _export_run(output / "baseline", version="expense-agent-v1", profile="reference")
    candidate_report = _export_run(
        output / "candidate",
        version=args.candidate_version,
        profile=args.candidate_profile,
    )
    baseline = _load_episodes(output / "baseline" / "episodes")
    candidate = _load_episodes(output / "candidate" / "episodes")
    dataset_audit = _dataset_evidence(candidate)
    version_comparison = _compare_versions(baseline, candidate)
    process_quality = _process_quality(candidate)
    human_review = _human_review(args.human_review)
    baseline_failures = _failure_snapshot(baseline)
    candidate_failures = _failure_snapshot(candidate)

    from trace_debugger import evaluate_regression_gate

    failure_gate = evaluate_regression_gate(candidate_failures, baseline_failures)
    performance = _read_json(args.performance) if args.performance.exists() else None
    release = evaluate_evidence_bundle(
        episodes=candidate,
        process_quality=process_quality,
        failure_gate=failure_gate,
        performance_evidence=performance,
        dataset_audit=dataset_audit,
        version_comparison=version_comparison,
        human_review=human_review,
    )
    feedback = _feedback_queue(candidate, version_comparison, candidate_failures, human_review)
    report = {
        "schema_version": "agent-business-release/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "employee expense review",
        "baseline_run": baseline_report,
        "candidate_run": candidate_report,
        "dataset_audit": dataset_audit,
        "version_comparison": version_comparison,
        "process_quality": process_quality,
        "human_review": human_review,
        "failure_regression": failure_gate,
        "performance_evidence": performance,
        "release_decision": release,
        "feedback_queue": feedback,
        "evidence_boundary": {
            "business_data": "versioned synthetic claims modeled after an expense workflow",
            "human_review": "fixture contract unless replaced with a dated reviewer export",
            "deployment": "offline release exercise; no production traffic or automatic rollback",
        },
    }
    _write_json(output / "release_report.json", report)
    _write_json(output / "dataset_audit.json", dataset_audit)
    _write_json(output / "version_comparison.json", version_comparison)
    _write_json(output / "process_quality.json", process_quality)
    _write_json(output / "human_review.json", human_review)
    _write_json(output / "failure_gate.json", failure_gate)
    _write_json(output / "feedback_queue.json", feedback)
    print(json.dumps(release, ensure_ascii=False, indent=2))
    print(f"release report: {output / 'release_report.json'}")
    return 0 if release["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
