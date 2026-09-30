"""Soft multimodal process scores become release evidence only after calibration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from eval_engine.gates.release_audit import audit_release

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "fixtures" / "episodes"
CALIBRATION = _load_path = (
    ROOT / "examples" / "fixtures" / "calibration" / "multimodal_dimension_held_out.json"
)
OK = FIXTURES / "multimodal_step_ok.json"
BAD = FIXTURES / "multimodal_step_bad.json"
VIDEO_OK = FIXTURES / "multimodal_step_video_ok.json"
VIDEO_BAD = FIXTURES / "multimodal_step_video_bad.json"
DIGEST = "0b457c939a634c18a4b31332846b0f6fd96237b3c346fd36fb7f2c97ac96a9ad"
VIDEO_DIGEST = "742bb37209598fde51cd6c548ac5fcdfeae75b6bf545937b0a7bb55ef8599a73"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CALIBRATION_DOC = _load(CALIBRATION)


def _audit(path: Path, **kwargs):
    return audit_release([_load(path)], calibration=CALIBRATION_DOC, **kwargs)


def test_audit_report_carries_attribution_anchor_block():
    """锚点交叉校验必须出现在审计报告里；trace-debugger 缺失时记 skipped 而非失败。"""
    report = _audit(OK)
    block = report["attribution_anchors"]
    assert "anchor_consistency" in block
    assert "anchor_total" in block
    assert "note" in block
    assert isinstance(block["skipped"], list)
    assert isinstance(block["per_episode"], list)


def test_calibrated_image_and_video_good_paths_pass():
    image = _audit(OK)
    video = _audit(VIDEO_OK, generation_appendix={"note": "optional aux only; not a gate"})
    for report, digest, tool in (
        (image, DIGEST, "generate_image"),
        (video, VIDEO_DIGEST, "generate_video"),
    ):
        assert report["decision"] == "pass"
        assert report["decision_basis"] == "process_reward_soft_dimensions"
        assert report["hard_failures"] == []
        assert report["process_quality"]["overall_score"] >= 3.5
        assert report["calibration"]["gate_split"] == "held_out"
        assert report["calibration"]["sample_size"] == 12
        assert isinstance(report["calibration"]["kappa"], float)
        assert report["calibration"]["kappa_unit"] == "dimension_cell"
        assert report["calibration"]["episode_count"] == 1
        assert "bootstrap" in report["calibration"]
        assert "kappa" in report["calibration"]["bootstrap"]
        assert "by_split" in report["calibration"]
        assert report["calibration"]["by_split"]["held_out"]["sample_size"] == 12
        assert "exact_agree_rate" in report["calibration"]
        assert "pairs" in report["calibration"]
        digests = [
            item["sha256"]
            for step in report["process_quality"]["steps"]
            for item in step["artifacts"]
        ]
        assert digest in digests
        generate = next(
            step for step in report["process_quality"]["steps"] if step["tool_name"] == tool
        )
        values = [item["score"] for item in generate["rubrics"]]
        assert generate["step_score"] == round(sum(values) / len(values), 3)
        assert min(values) != generate["step_score"] or len(set(values)) == 1
        assert 2 in values or 4 in values or 3 in values or 5 in values
    assert video["auxiliary_evidence"]["note"].startswith("optional")


def test_defective_paths_review_on_soft_score_not_hold():
    image = _audit(BAD)
    video = _audit(VIDEO_BAD)
    assert image["decision"] == "review"
    assert video["decision"] == "review"
    assert image["hard_failures"] == []
    assert video["hard_failures"] == []
    assert image["process_quality"]["overall_score"] < 3.5
    assert video["process_quality"]["overall_score"] < 3.5
    image_generate = next(
        step for step in image["process_quality"]["steps"] if step["tool_name"] == "generate_image"
    )
    video_final = next(
        step for step in video["process_quality"]["steps"] if step["step_kind"] == "final"
    )
    assert [item["score"] for item in image_generate["rubrics"]] == [2.0, 2.0, 3.0, 4.0]
    assert [item["score"] for item in video_final["rubrics"]] != [2.0, 2.0, 3.0, 4.0]
    assert {item["failure_type"] for item in image["rule_findings"]} == {"unnecessary_generation"}
    assert {item["failure_type"] for item in video["rule_findings"]} == {"ungrounded_vision"}
    assert all(step["tool_name"] != "thought" for step in image["process_quality"]["steps"])


def test_episodes_are_gated_separately():
    report = audit_release([_load(OK), _load(BAD)], calibration=CALIBRATION_DOC)
    assert report["decision"] == "review"
    assert report["process_quality"] is None
    scores = {
        episode["episode_id"]: episode["process_quality"]["overall_score"]
        for episode in report["episodes"]
    }
    assert scores["mm-step-read-write-ok-001"] >= 3.5
    assert scores["mm-step-bad-ungrounded-001"] < 3.5
    assert report["calibration"]["episode_ids"] == [
        "mm-step-bad-ungrounded-001",
        "mm-step-read-write-ok-001",
    ]


def test_mismatched_judge_score_stays_uncalibrated():
    broken = json.loads(json.dumps(CALIBRATION_DOC))
    broken["items"][0]["judge_score"] = 1
    report = audit_release([_load(OK)], calibration=broken)
    assert report["decision"] == "review"
    assert report["process_quality"] is None
    assert report["decision_basis"] == "uncalibrated"


def test_uncalibrated_rule_findings_are_not_the_process_conclusion():
    report = audit_release([_load(BAD)])
    assert report["decision"] == "review"
    assert report["process_quality"] is None
    assert report["decision_basis"] == "uncalibrated"
    assert report["rule_findings"]
    assert not any("below" in reason for reason in report["review_reasons"])


def test_cli_matches_library_on_image_and_video():
    script = ROOT / "examples" / "run_release_audit.py"
    for path, expected in (
        (OK, "pass"),
        (BAD, "review"),
        (VIDEO_OK, "pass"),
        (VIDEO_BAD, "review"),
    ):
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                str(path),
                "--calibration",
                str(CALIBRATION),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            check=False,
        )
        stdout = (completed.stdout or "").strip()
        assert stdout, completed.stderr
        # CLI may print a summary line to stderr; stdout is the JSON report.
        report = json.loads(stdout)
        assert report["decision"] == expected, completed.stderr
        assert completed.returncode == (0 if expected == "pass" else 1)
