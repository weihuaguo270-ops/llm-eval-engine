"""Understanding track must reach offline_real with real local media."""

from pathlib import Path

import pytest

pytest.importorskip("PIL")
pytest.importorskip("imageio")
pytest.importorskip("numpy")

from eval_engine.multimodal import (
    run_multimodal_offline_tracks,
    run_understanding_track,
    understanding_track_gate,
)


def test_smoke_understanding_track_reaches_offline_real(tmp_path: Path):
    report = run_understanding_track(tmp_path / "understanding", smoke=True)
    gate = report["track_gate"]
    assert gate["passed"] is True
    assert gate["evidence_level"] == "offline_real"
    assert gate["image_vqa_gate"]["checks"]["real_media"] is True
    assert gate["video_qa_gate"]["checks"]["real_media"] is True


def test_understanding_track_offline_real_summary(tmp_path: Path):
    report = run_multimodal_offline_tracks(
        tmp_path / "understanding",
        tracks=("understanding",),
        smoke=True,
    )
    assert report["all_tracks_offline_real"] is True
    assert report["summary"]["understanding"]["evidence_level"] == "offline_real"
    assert (tmp_path / "understanding" / "multimodal_offline_tracks_report.json").is_file()


def test_generation_track_rejected():
    with pytest.raises(ValueError, match="generation track removed"):
        run_multimodal_offline_tracks(".", tracks=("generation",), smoke=True)


def test_understanding_gate_fail_closed_on_empty_records():
    understanding = understanding_track_gate(image_records=[], video_records=[])
    assert understanding["passed"] is False
    assert understanding["evidence_level"] == "interface"
