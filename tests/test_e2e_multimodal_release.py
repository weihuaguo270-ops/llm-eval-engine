"""End-to-end multimodal release path through the cross-agent CLI."""

from __future__ import annotations

import json
from pathlib import Path

from examples.e2e_multimodal_release import run_scenario


def test_e2e_multimodal_release_pass_hold_and_review(tmp_path: Path):
    expected = {
        "pass": ("pass", 0),
        "hold-safety": ("hold", 1),
        "review-human": ("review", 1),
    }
    for scenario, (decision, exit_code) in expected.items():
        work = tmp_path / scenario
        result = run_scenario(scenario, work)
        assert result["release_decision"] == decision, result
        assert result["cli_exit_code"] == exit_code, result["cli_stderr"]
        assert result["multimodal_gate"] == decision
        assert result["evidence"]["multimodal_present"] is True
        release = json.loads(Path(result["paths"]["release"]).read_text(encoding="utf-8"))
        assert release["decision"] == decision
