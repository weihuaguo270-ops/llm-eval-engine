import pytest

from eval_engine.multimodal.video_benchmark import (
    build_video_prompt_dataset,
    video_artifact_record,
    video_completion_gate,
    video_dataset_manifest,
)


def test_video_dataset_has_30_prompts_and_held_out():
    report = video_dataset_manifest(build_video_prompt_dataset())
    assert report["case_count"] == 30
    assert report["split_counts"] == {"dev": 6, "golden": 15, "held_out": 9}


def test_video_artifact_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="missing video artifact"):
        video_artifact_record(tmp_path / "x.mp4", case={"id": "v", "split": "dev", "prompt": "x"},
                              model={"id": "m", "revision": "r", "license": "l", "alias": "m"},
                              seed=1, latency_ms=1, config={"fps": 8})


def test_video_gate_rejects_empty_records():
    gate = video_completion_gate([])
    assert gate["passed"] is False
    assert gate["evidence_level"] == "interface"
