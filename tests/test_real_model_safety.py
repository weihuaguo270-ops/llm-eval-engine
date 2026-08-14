from eval_engine.safety.real_model_suite import (
    analyze_real_safety_run, build_safety_dataset, safety_dataset_manifest,
)

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "examples" / "run_real_safety_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_real_safety_benchmark", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_real_safety_dataset_is_frozen_and_has_held_out():
    report = safety_dataset_manifest(build_safety_dataset())
    assert report["case_count"] == 30
    assert report["split_counts"] == {"dev": 6, "golden": 15, "held_out": 9}
    assert report["attack_count"] == 20
    assert report["benign_count"] == 10


def test_real_safety_gate_requires_real_run_fingerprints():
    cases = build_safety_dataset()
    runs = []
    for case in cases:
        benign = "benign" in case["tags"]
        runs.append({"case_id": case["id"], "decision": "allow" if benign else case["expected_decision"],
                     "tool_calls": case["required_tools"], "output": "safe"})
    report = analyze_real_safety_run(cases, runs, model="test", run_date="fixed")
    assert report["completion_gate"]["passed"] is False
    for row in runs:
        row["response_fingerprint"] = "a" * 64
    report = analyze_real_safety_run(cases, runs, model="test", run_date="fixed")
    assert report["completion_gate"]["passed"] is True
    assert report["unsafe_authorization_rate"] == 0.0


def test_policy_protocol_separates_authorized_and_blocked_tools():
    parsed = RUNNER.parse_message({"content": '{"decision":"deny",'
        '"authorized_tool_calls":[],"blocked_tool_calls":["read_secret"],"reason":"blocked"}'})
    assert parsed["tool_calls"] == []
    assert parsed["blocked_tool_calls"] == ["read_secret"]
