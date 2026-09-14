"""Smoke the staged real understanding benchmark CLI helpers."""

import importlib.util
from pathlib import Path

from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle
from eval_engine.multimodal import build_understanding_predictor


SCRIPT = Path(__file__).parents[1] / "examples" / "run_real_understanding_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_real_understanding_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_build_understanding_predictor_factory():
    sidecar = build_understanding_predictor(adapter="sidecar", model_id="local/a")
    noisy = build_understanding_predictor(adapter="noisy_sidecar", model_id="local/b")
    assert sidecar.adapter_name == "sidecar"
    assert noisy.noisy is True
    try:
        build_understanding_predictor(adapter="nope")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unsupported understanding adapter" in str(exc)


def test_smoke_pipeline_reaches_offline_real_and_release_evidence(tmp_path):
    MODULE.initialize(tmp_path)
    materialize = MODULE.materialize(tmp_path, smoke=True)
    assert materialize["image_real_media"] is True
    assert materialize["video_real_media"] is True

    predict = MODULE.predict(tmp_path, smoke=True)
    assert predict["records"] == 8  # 2 modalities * 2 cases * 2 models
    score = MODULE.score(tmp_path, smoke=True)
    assert score["scored"] == 8

    report = MODULE.finalize(tmp_path, smoke=True)
    assert report["track_gate"]["passed"] is True
    assert report["track_gate"]["evidence_level"] == "offline_real"
    assert report["held_out_image_report"]["passed"] is True
    assert report["held_out_video_report"]["passed"] is True
    evidence = report["multimodal_understanding_evidence"]
    assert evidence["schema_version"] == "multimodal-understanding-evidence/v1"
    assert evidence["passed"] is True
    assert (tmp_path / "smoke_multimodal_understanding_evidence.json").is_file()
    assert (tmp_path / "smoke_dataset_audit.json").is_file()

    bundle = evaluate_evidence_bundle(
        episodes=[
            {
                "schema_version": "evaluation-episode/v1",
                "episode_id": "e1",
                "split": "held_out",
                "state_verification": {"passed": True},
            }
        ],
        multimodal_understanding=evidence,
        dataset_audit=report["dataset_audit"],
    )
    assert bundle["decision"] == "pass"
    assert bundle["evidence"]["multimodal_understanding_present"] is True


def test_video_materialize_exports_preview_frame(tmp_path):
    MODULE.initialize(tmp_path)
    payload = MODULE.materialize(tmp_path, smoke=True)
    video_cases = MODULE.read_json(tmp_path / "smoke_materialized.json", {})["video_cases"]
    assert payload["video_cases"] == 2
    preview = Path(video_cases[0]["artifact"]["preview_frame_uri"])
    assert preview.is_file()
    assert preview.suffix == ".png"
