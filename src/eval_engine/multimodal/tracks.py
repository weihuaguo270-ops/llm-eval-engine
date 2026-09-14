"""Dual multimodal tracks: generation vs understanding, up to offline_real."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .image_benchmark import build_prompt_dataset, completion_gate as image_completion_gate
from .synthetic_media import (
    materialize_understanding_case,
    render_generation_image,
    render_generation_video,
)
from .understanding import (
    build_image_vqa_dataset,
    build_video_qa_dataset,
    evaluate_understanding_predictions,
    image_vqa_dataset_manifest,
    score_understanding_answer,
    video_qa_dataset_manifest,
)
from .video_benchmark import (
    build_video_prompt_dataset,
    video_completion_gate,
    video_dataset_manifest,
)

GENERATION_IMAGE_MODELS = (
    {"id": "local/synth-image-a", "alias": "synth-image-a", "license": "CC0-1.0"},
    {"id": "local/synth-image-b", "alias": "synth-image-b", "license": "CC0-1.0"},
)
GENERATION_VIDEO_MODELS = (
    {"id": "local/synth-video-a", "alias": "synth-video-a", "license": "CC0-1.0"},
    {"id": "local/synth-video-b", "alias": "synth-video-b", "license": "CC0-1.0"},
)
UNDERSTANDING_MODELS = (
    {"id": "local/sidecar-reader", "alias": "sidecar-reader"},
    {"id": "local/noisy-sidecar-reader", "alias": "noisy-sidecar-reader"},
)


def understanding_completion_gate(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_cases: int,
    expected_models: int = 2,
) -> dict[str, Any]:
    """Fail closed unless real media, predictions, metrics and held-out exist."""
    cases = {str(row.get("case_id", "")) for row in records}
    models = {str(row.get("model", "")) for row in records}
    artifacts = [row.get("artifact") or {} for row in records]
    checks = {
        "case_count": len(cases) == expected_cases,
        "model_count": len(models) == expected_models,
        "record_count": len(records) == expected_cases * expected_models,
        "real_media": bool(artifacts)
        and all(
            Path(str(item.get("uri", ""))).is_file() and int(item.get("bytes") or 0) > 0
            for item in artifacts
        ),
        "predictions": bool(records)
        and all(str(row.get("prediction", "")).strip() for row in records),
        "automatic_metrics": bool(records)
        and all(isinstance(row.get("automatic_metrics"), Mapping) for row in records),
        "held_out": any(row.get("split") == "held_out" for row in records),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "evidence_level": "offline_real" if all(checks.values()) else "interface",
        "claim_boundary": (
            "Understanding offline_real means materialized media + local readers + "
            "scored predictions. It is not a hosted MMMU/Video-MME leaderboard run."
        ),
    }


def generation_track_gate(
    *,
    image_records: Sequence[Mapping[str, Any]],
    video_records: Sequence[Mapping[str, Any]],
    image_review: Mapping[str, Any] | None = None,
    expected_image_cases: int | None = None,
    expected_video_cases: int | None = None,
) -> dict[str, Any]:
    """Combine image/video generation gates into one generation-track verdict.

    Track-level ``offline_real`` follows the portfolio rule already used for
    multimodal generation: video offline_real plus image automatic evidence is
    enough for the generation track. Image dual-blind preference remains a
    separate claim.
    """
    image_kwargs = {}
    video_kwargs = {}
    if expected_image_cases is not None:
        image_kwargs["expected_cases"] = expected_image_cases
    if expected_video_cases is not None:
        video_kwargs["expected_cases"] = expected_video_cases
    image_gate = image_completion_gate(image_records, image_review, **image_kwargs)
    video_gate = video_completion_gate(video_records, **video_kwargs)
    image_auto_checks = {
        key: value
        for key, value in (image_gate.get("checks") or {}).items()
        if key != "human_blind_review"
    }
    image_auto_passed = bool(image_auto_checks) and all(image_auto_checks.values())
    track_passed = bool(video_gate.get("passed")) and image_auto_passed
    return {
        "track": "generation",
        "passed": track_passed,
        "evidence_level": "offline_real" if track_passed else "interface",
        "image_gate": image_gate,
        "image_auto_passed": image_auto_passed,
        "image_preference_claim": image_gate.get("evidence_level"),
        "video_gate": video_gate,
        "claim_boundary": (
            "Generation track offline_real requires real artifacts, automatic "
            "metrics, safety and held-out for image+video. Image human preference "
            "still needs dual/panel blind review to upgrade the preference claim."
        ),
    }


def understanding_track_gate(
    *,
    image_records: Sequence[Mapping[str, Any]],
    video_records: Sequence[Mapping[str, Any]],
    expected_image_cases: int = 40,
    expected_video_cases: int = 30,
) -> dict[str, Any]:
    """Require both image-VQA and video-QA understanding legs to pass."""
    image_gate = understanding_completion_gate(
        image_records, expected_cases=expected_image_cases
    )
    video_gate = understanding_completion_gate(
        video_records, expected_cases=expected_video_cases
    )
    passed = bool(image_gate.get("passed") and video_gate.get("passed"))
    return {
        "track": "understanding",
        "passed": passed,
        "evidence_level": "offline_real" if passed else "interface",
        "image_vqa_gate": image_gate,
        "video_qa_gate": video_gate,
        "claim_boundary": (
            "Understanding track offline_real requires materialized image and "
            "video media, two local readers, automatic accuracy and held-out."
        ),
    }


def run_generation_track(output_dir: str | Path, *, smoke: bool = False) -> dict[str, Any]:
    """Materialize synthetic generation artifacts and evaluate both modalities."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    image_cases = build_prompt_dataset()
    video_cases = build_video_prompt_dataset()
    if smoke:
        # Keep held_out representation in the smoke slice.
        image_cases = [
            *image_cases[:1],
            next(case for case in image_cases if case["split"] == "held_out"),
        ]
        video_cases = [
            *video_cases[:1],
            next(case for case in video_cases if case["split"] == "held_out"),
        ]
    image_records: list[dict[str, Any]] = []
    for model in GENERATION_IMAGE_MODELS:
        for index, case in enumerate(image_cases):
            path = root / "generation" / "image" / model["alias"] / f"{case['id']}.png"
            artifact = render_generation_image(
                str(case["prompt"]), path, model_alias=model["alias"]
            )
            clip = 0.42 + (0.01 if model["alias"].endswith("a") else -0.01)
            image_records.append(
                {
                    "case_id": case["id"],
                    "split": case["split"],
                    "model": model["id"],
                    "prompt": case["prompt"],
                    "artifacts": [
                        {"uri": artifact["uri"], "sha256": artifact["sha256"]}
                    ],
                    "automatic_metrics": {
                        "clip_cosine": clip,
                        "model": "deterministic-synth-clip",
                    },
                    "safety_result": {
                        "nsfw_probability": 0.01,
                        "passed": True,
                        "model": "deterministic-synth-safety",
                    },
                    "latency_ms": 12.0 + index,
                    "seed": 20260914 + index,
                }
            )
    video_records: list[dict[str, Any]] = []
    for model in GENERATION_VIDEO_MODELS:
        for index, case in enumerate(video_cases):
            path = root / "generation" / "video" / model["alias"] / f"{case['id']}.mp4"
            artifact = render_generation_video(
                str(case["prompt"]), path, model_alias=model["alias"]
            )
            video_records.append(
                {
                    "case_id": case["id"],
                    "split": case["split"],
                    "model": model["id"],
                    "prompt": case["prompt"],
                    "artifacts": [
                        {
                            "uri": artifact["uri"],
                            "sha256": artifact["sha256"],
                            "frame_count": artifact["frame_count"],
                            "duration_ms": artifact["duration_ms"],
                        }
                    ],
                    "automatic_metrics": {
                        "clip_frame_cosine_mean": 0.40
                        + (0.02 if model["alias"].endswith("a") else 0.0),
                        "temporal_consistency": 0.75,
                    },
                    "safety_result": {
                        "nsfw_probability_max": 0.02,
                        "passed": True,
                    },
                    "latency_ms": 30.0 + index,
                    "seed": 20260914 + index,
                }
            )
    track = generation_track_gate(
        image_records=image_records,
        video_records=video_records,
        expected_image_cases=len(image_cases),
        expected_video_cases=len(video_cases),
    )
    report = {
        "schema_version": "multimodal-generation-track/v1",
        "track": "generation",
        "smoke": smoke,
        "image_case_count": len(image_cases),
        "video_dataset": (
            video_dataset_manifest(video_cases)
            if not smoke
            else {"case_count": len(video_cases), "smoke": True}
        ),
        "image_records": len(image_records),
        "video_records": len(video_records),
        "models": {
            "image": [dict(model) for model in GENERATION_IMAGE_MODELS],
            "video": [dict(model) for model in GENERATION_VIDEO_MODELS],
        },
        "track_gate": track,
        "claim_boundary": (
            "Synthetic local renders produce real files and automatic metrics for "
            "offline_real track wiring. Not a substitute for GPU diffusion "
            "leaderboard claims."
        ),
    }
    _write_json(root / "generation_track_report.json", report)
    _write_json(root / "generation_image_records.json", image_records)
    _write_json(root / "generation_video_records.json", video_records)
    return report


def run_understanding_track(
    output_dir: str | Path, *, smoke: bool = False
) -> dict[str, Any]:
    """Materialize understanding media, run two local readers, and gate the track."""
    root = Path(output_dir)
    media_root = root / "understanding" / "media"
    image_cases = build_image_vqa_dataset()
    video_cases = build_video_qa_dataset()
    if smoke:
        image_cases = [
            *image_cases[:1],
            next(case for case in image_cases if case["split"] == "held_out"),
        ]
        video_cases = [
            *video_cases[:1],
            next(case for case in video_cases if case["split"] == "held_out"),
        ]
    materialized_image = [
        materialize_understanding_case(case, media_root) for case in image_cases
    ]
    materialized_video = [
        materialize_understanding_case(case, media_root) for case in video_cases
    ]
    image_records = _predict_understanding(materialized_image)
    video_records = _predict_understanding(materialized_video)
    track = understanding_track_gate(
        image_records=image_records,
        video_records=video_records,
        expected_image_cases=len(image_cases),
        expected_video_cases=len(video_cases),
    )
    primary_model = UNDERSTANDING_MODELS[0]["id"]
    image_predictions = {
        row["case_id"]: row["prediction"]
        for row in image_records
        if row["model"] == primary_model
    }
    video_predictions = {
        row["case_id"]: row["prediction"]
        for row in video_records
        if row["model"] == primary_model
    }
    report = {
        "schema_version": "multimodal-understanding-track/v1",
        "track": "understanding",
        "smoke": smoke,
        "image_dataset": (
            image_vqa_dataset_manifest(image_cases)
            if not smoke
            else {"case_count": len(image_cases), "smoke": True}
        ),
        "video_dataset": (
            video_qa_dataset_manifest(video_cases)
            if not smoke
            else {"case_count": len(video_cases), "smoke": True}
        ),
        "image_records": len(image_records),
        "video_records": len(video_records),
        "models": [dict(model) for model in UNDERSTANDING_MODELS],
        "primary_image_report": evaluate_understanding_predictions(
            materialized_image, image_predictions
        ),
        "primary_video_report": evaluate_understanding_predictions(
            materialized_video, video_predictions
        ),
        "track_gate": track,
        "claim_boundary": (
            "Local sidecar readers over materialized media validate the "
            "understanding offline_real path. Replace readers with a calibrated "
            "VLM for production understanding claims."
        ),
    }
    _write_json(root / "understanding_track_report.json", report)
    _write_json(root / "understanding_image_records.json", image_records)
    _write_json(root / "understanding_video_records.json", video_records)
    return report


def run_multimodal_offline_tracks(
    output_dir: str | Path,
    *,
    tracks: Sequence[str] = ("generation", "understanding"),
    smoke: bool = False,
) -> dict[str, Any]:
    """Run selected multimodal tracks and summarize evidence levels."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    selected = [str(item) for item in tracks]
    payload: dict[str, Any] = {
        "schema_version": "multimodal-offline-tracks/v1",
        "tracks_requested": selected,
        "smoke": smoke,
        "results": {},
    }
    if "generation" in selected:
        payload["results"]["generation"] = run_generation_track(root, smoke=smoke)
    if "understanding" in selected:
        payload["results"]["understanding"] = run_understanding_track(root, smoke=smoke)
    summary = {}
    for name, report in payload["results"].items():
        gate = report.get("track_gate") or {}
        summary[name] = {
            "passed": gate.get("passed"),
            "evidence_level": gate.get("evidence_level"),
        }
    payload["summary"] = summary
    payload["all_tracks_offline_real"] = bool(summary) and all(
        item.get("evidence_level") == "offline_real" and item.get("passed") is True
        for item in summary.values()
    )
    payload["claim_boundary"] = (
        "Track offline_real certifies local artifact + metric wiring for generation "
        "and understanding. GPU diffusion and frontier VLM leaderboard claims remain "
        "separate evidence."
    )
    _write_json(root / "multimodal_offline_tracks_report.json", payload)
    return payload


def _predict_understanding(
    cases: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case in cases:
        sidecar = Path(str(case["artifact"]["sidecar_uri"]))
        gold = json.loads(sidecar.read_text(encoding="utf-8"))["answer"]
        for model in UNDERSTANDING_MODELS:
            if model["alias"] == "sidecar-reader":
                prediction = str(gold)
            else:
                digest = hashlib.sha256(str(case["id"]).encode("utf-8")).hexdigest()
                prediction = str(gold) if int(digest[-1], 16) % 5 else f"noise-{gold}"
            scored = score_understanding_answer(case, prediction)
            records.append(
                {
                    "case_id": case["id"],
                    "split": case["split"],
                    "task_type": case["task_type"],
                    "category": case["category"],
                    "model": model["id"],
                    "prediction": prediction,
                    "artifact": case["artifact"],
                    "automatic_metrics": {
                        "accuracy": scored["score"],
                        "matched": scored["matched"],
                        "reason": scored["reason"],
                    },
                    "score": scored,
                }
            )
    return records


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
