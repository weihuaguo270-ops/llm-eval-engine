"""Live Judge soft dimensions for release-audit media steps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_engine.core.multimodal_process_judge import (
    DIMENSIONS,
    extract_dimension_scores,
    make_live_dimension_judge,
)
from eval_engine.gates.release_audit import (
    audit_release,
    rebuild_held_out_calibration,
)
from eval_engine.integrations.episode import import_episode
from eval_engine.core.trajectory_parser import parse_trajectory

ROOT = Path(__file__).resolve().parents[1]
OK = ROOT / "examples" / "fixtures" / "episodes" / "multimodal_step_ok.json"
CALIBRATION = (
    ROOT / "examples" / "fixtures" / "calibration" / "multimodal_dimension_held_out.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _mock_llm(fixed: dict[str, float]):
    calls: list[str] = []

    def call(prompt: str) -> dict:
        calls.append(prompt)
        return {
            "role_understanding": "media step",
            "rubrics": [
                {
                    "dimension": name,
                    "score": fixed[name],
                    "reason": "mock",
                }
                for name in DIMENSIONS
            ],
            "step_score": sum(fixed.values()) / len(fixed),
            "needs_revision": False,
        }

    call.calls = calls  # type: ignore[attr-defined]
    return call


def test_live_judge_scores_media_steps_and_skips_thought():
    raw = _load(OK)
    dag = parse_trajectory(import_episode(raw).trajectory)
    # Pre-filled fixture scores must not leak into live mode.
    for node in dag.nodes:
        if node.tool_name == "generate_image":
            node.metadata["judge_scores"] = {
                "media_timing": 1,
                "media_arg_fidelity": 1,
                "artifact_attachment": 1,
                "media_safety": 1,
            }
    fixed = {
        "media_timing": 4,
        "media_arg_fidelity": 4,
        "artifact_attachment": 4,
        "media_safety": 5,
    }
    llm = _mock_llm(fixed)
    judge = make_live_dimension_judge(dag, llm)
    results = [judge("ignored") for _ in dag.nodes]
    thought = results[0]
    assert thought["rubrics"][0]["dimension"] == "context"
    assert len(llm.calls) == 3  # generate + describe + final
    for result in results[1:]:
        assert [r["dimension"] for r in result["rubrics"]] == list(DIMENSIONS)
        assert [r["score"] for r in result["rubrics"]] == [4.0, 4.0, 4.0, 5.0]
    media_node = next(n for n in dag.nodes if n.tool_name == "generate_image")
    assert media_node.metadata["judge_scores"] == {
        "media_timing": 4.0,
        "media_arg_fidelity": 4.0,
        "artifact_attachment": 4.0,
        "media_safety": 5.0,
    }


def test_live_scores_against_fixture_calibration_stay_uncalibrated():
    raw = _load(OK)
    fixed = {
        "media_timing": 1,
        "media_arg_fidelity": 1,
        "artifact_attachment": 1,
        "media_safety": 1,
    }
    report = audit_release(
        [raw],
        judge_factory=lambda dag: make_live_dimension_judge(dag, _mock_llm(fixed)),
        calibration=_load(CALIBRATION),
    )
    assert report["decision_basis"] == "uncalibrated"
    assert report["process_quality"] is None
    assert report["decision"] == "review"


def test_rebuild_calibration_binds_live_scores_into_gate():
    raw = _load(OK)
    fixed = {
        "media_timing": 5,
        "media_arg_fidelity": 4,
        "artifact_attachment": 5,
        "media_safety": 5,
    }
    report = audit_release(
        [raw],
        judge_factory=lambda dag: make_live_dimension_judge(dag, _mock_llm(fixed)),
        calibration=_load(CALIBRATION),
        rebuild_calibration=True,
    )
    assert report["decision_basis"] == "process_reward_soft_dimensions"
    assert report["calibration"]["sample_size"] == 12
    assert isinstance(report["calibration"]["kappa"], float)
    assert report["calibration"]["kappa_unit"] == "dimension_cell"
    assert report["calibration"]["bootstrap"]["kappa"]["low"] <= report["calibration"]["bootstrap"]["kappa"]["high"]
    assert report["process_quality"] is not None
    rebuilt = report["rebuilt_calibration"]
    assert rebuilt is not None
    live_rows = [
        row
        for row in rebuilt["items"]
        if row["step_index"] == 1 and row["dimension"] == "media_timing"
    ]
    assert live_rows[0]["judge_score"] == 5.0
    assert live_rows[0]["human_score"] is not None


def test_extract_dimension_scores_requires_all_four():
    with pytest.raises(ValueError, match="missing dimensions"):
        extract_dimension_scores(
            {"rubrics": [{"dimension": "media_timing", "score": 4}]}
        )


def test_rebuild_held_out_calibration_helper():
    prior = _load(CALIBRATION)
    cells = {
        "mm-step-read-write-ok-001": [
            (1, "media_timing", 2.0),
            (1, "media_arg_fidelity", 2.0),
            (1, "artifact_attachment", 2.0),
            (1, "media_safety", 2.0),
            (2, "media_timing", 2.0),
            (2, "media_arg_fidelity", 2.0),
            (2, "artifact_attachment", 2.0),
            (2, "media_safety", 2.0),
            (3, "media_timing", 2.0),
            (3, "media_arg_fidelity", 2.0),
            (3, "artifact_attachment", 2.0),
            (3, "media_safety", 2.0),
        ]
    }
    rebuilt = rebuild_held_out_calibration(prior, cells)
    assert all(row["judge_score"] == 2.0 for row in rebuilt["items"])
    assert len(rebuilt["items"]) == 12
