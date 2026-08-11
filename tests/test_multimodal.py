import pytest

from eval_engine.multimodal import (
    ArtifactIntegrityMetric,
    ArtifactRef,
    CallableMetricAdapter,
    MultimodalEvaluator,
    aggregate_human_ratings,
    metric_catalog,
)


def test_integrity_metric_for_image_and_video():
    case = {
        "id": "media-1",
        "prompt": "a red car turns left",
        "output_artifacts": [
            {
                "id": "image-1",
                "media_type": "image",
                "uri": "artifacts/image.png",
                "mime_type": "image/png",
                "width": 1024,
                "height": 768,
            },
            {
                "id": "video-1",
                "media_type": "video",
                "uri": "artifacts/video.mp4",
                "mime_type": "video/mp4",
                "duration_ms": 2000,
                "frame_count": 48,
            },
        ],
    }
    report = MultimodalEvaluator().evaluate(case)
    assert report["passed"] is True
    assert report["overall_score"] == 1.0
    assert report["media_types"] == ["image", "video"]


def test_integrity_metric_detects_missing_video_metadata():
    case = {
        "id": "media-2",
        "output_artifacts": [
            {"id": "video-1", "media_type": "video", "uri": "video.mp4"}
        ],
    }
    report = MultimodalEvaluator().evaluate(case)
    assert report["passed"] is False
    assert report["metrics"][0]["details"]["artifacts"][0]["missing_metadata"] == [
        "duration_ms",
        "frame_count",
    ]


def test_callable_semantic_metric_and_human_ratings():
    metric = CallableMetricAdapter(
        "prompt_adherence",
        lambda case, artifacts: {"score": 0.82, "model": "fixture-vlm"},
        threshold=0.8,
        media_types=("image",),
    )
    case = {
        "id": "image-judge",
        "prompt": "a diagram",
        "output_artifacts": [
            {
                "id": "image-1",
                "media_type": "image",
                "uri": "diagram.png",
                "width": 10,
                "height": 10,
            }
        ],
        "human_ratings": [
            {"annotator": "r1", "scores": {"prompt_adherence": 4}},
            {"annotator": "r2", "scores": {"prompt_adherence": 5}},
        ],
    }
    report = MultimodalEvaluator([ArtifactIntegrityMetric(), metric]).evaluate(case)
    assert report["passed"] is True
    assert report["metrics"][1]["details"]["model"] == "fixture-vlm"
    assert report["human_ratings"]["dimensions"]["prompt_adherence"]["mean"] == 4.5


def test_artifact_ref_rejects_embedded_bytes():
    with pytest.raises(ValueError, match="embedded media bytes"):
        ArtifactRef.from_dict(
            {
                "id": "x",
                "media_type": "image",
                "uri": "memory://x",
                "base64": "abc",
            }
        )


def test_metric_catalog_marks_heavy_metrics_as_adapters():
    catalog = {item["name"]: item["status"] for item in metric_catalog()}
    assert catalog["artifact_integrity"] == "built_in"
    assert catalog["FVD/VBench"] == "adapter_required"
    assert catalog["VLM Judge"] == "calibrated_adapter_required"


def test_human_rating_scale_is_enforced():
    with pytest.raises(ValueError, match="1-5"):
        aggregate_human_ratings([{"scores": {"quality": 6}}])

def test_lower_is_better_metric_uses_normalized_score():
    metric = CallableMetricAdapter(
        "fid",
        lambda case, artifacts: 12.0,
        threshold=20.0,
        media_types=("image",),
        higher_is_better=False,
        score_range=(0.0, 100.0),
    )
    report = MultimodalEvaluator([metric]).evaluate(
        {
            "id": "fid-1",
            "output_artifacts": [
                {
                    "id": "image-1",
                    "media_type": "image",
                    "uri": "image.png",
                    "width": 10,
                    "height": 10,
                }
            ],
        }
    )
    assert report["passed"] is True
    assert report["metrics"][0]["score"] == 12.0
    assert report["metrics"][0]["normalized_score"] == 0.88
    assert report["overall_score"] == 0.88


def test_no_artifacts_does_not_pass():
    report = MultimodalEvaluator().evaluate({"id": "empty", "output_artifacts": []})
    assert report["passed"] is False
    assert report["overall_score"] is None
