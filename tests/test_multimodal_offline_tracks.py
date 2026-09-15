"""Dual multimodal tracks must reach offline_real with real local media."""

from pathlib import Path

import pytest

pytest.importorskip("PIL")
pytest.importorskip("imageio")
pytest.importorskip("numpy")

from eval_engine.multimodal import (
    generation_track_gate,
    run_generation_track,
    run_multimodal_offline_tracks,
    run_understanding_track,
    understanding_track_gate,
)


def test_smoke_generation_track_reaches_offline_real(tmp_path: Path):
    report = run_generation_track(tmp_path / "generation", smoke=True)
    gate = report["track_gate"]
    assert gate["passed"] is True
    assert gate["evidence_level"] == "offline_real"
    assert gate["image_auto_passed"] is True
    assert gate["video_gate"]["passed"] is True
    # Preference claim stays blocked without human review.
    assert gate["image_gate"]["checks"]["human_blind_review"] is False


def test_smoke_understanding_track_reaches_offline_real(tmp_path: Path):
    report = run_understanding_track(tmp_path / "understanding", smoke=True)
    gate = report["track_gate"]
    assert gate["passed"] is True
    assert gate["evidence_level"] == "offline_real"
    assert gate["image_vqa_gate"]["checks"]["real_media"] is True
    assert gate["video_qa_gate"]["checks"]["real_media"] is True


def test_both_tracks_offline_real_summary(tmp_path: Path):
    report = run_multimodal_offline_tracks(
        tmp_path / "both",
        tracks=("generation", "understanding"),
        smoke=True,
    )
    assert report["all_tracks_offline_real"] is True
    assert report["summary"]["generation"]["evidence_level"] == "offline_real"
    assert report["summary"]["understanding"]["evidence_level"] == "offline_real"
    assert (tmp_path / "both" / "multimodal_offline_tracks_report.json").is_file()


def test_track_gates_fail_closed_on_empty_records():
    generation = generation_track_gate(image_records=[], video_records=[])
    understanding = understanding_track_gate(image_records=[], video_records=[])
    assert generation["passed"] is False
    assert generation["evidence_level"] == "interface"
    assert understanding["passed"] is False
    assert understanding["evidence_level"] == "interface"
