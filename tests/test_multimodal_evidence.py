"""Tests for multimodal release evidence and productized metric adapters."""

from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle
from eval_engine.multimodal import (
    ArtifactIntegrityMetric,
    ClipScoreMetric,
    MultimodalEvaluator,
    SafetyClassifierMetric,
    build_multimodal_evidence,
    build_video_dimension_scores,
)
from eval_engine.multimodal.evidence import summarize_case_reports


def _image_case(**overrides):
    case = {
        "id": "img-1",
        "split": "held_out",
        "prompt": "a red car",
        "output_artifacts": [
            {
                "id": "image-1",
                "media_type": "image",
                "uri": "artifacts/image.png",
                "width": 512,
                "height": 512,
            }
        ],
        "automatic_metrics": {"clip_cosine": 0.41, "model": "fixture-clip"},
        "safety_result": {"nsfw_probability": 0.02, "passed": True},
    }
    case.update(overrides)
    return case


def test_clip_and_safety_adapters_consume_precomputed_fields():
    report = MultimodalEvaluator(
        [ArtifactIntegrityMetric(), ClipScoreMetric(), SafetyClassifierMetric()]
    ).evaluate(_image_case())
    assert report["passed"] is True
    by_name = {item["name"]: item for item in report["metrics"]}
    assert by_name["clip_score"]["score"] == 0.41
    assert by_name["safety_classifier"]["passed"] is True
    assert by_name["safety_classifier"]["normalized_score"] == 0.98


def test_safety_adapter_fails_closed_on_nsfw():
    report = MultimodalEvaluator([SafetyClassifierMetric()]).evaluate(
        _image_case(safety_result={"nsfw_probability": 0.81, "passed": False})
    )
    assert report["passed"] is False
    assert report["metrics"][0]["passed"] is False


def test_build_multimodal_evidence_holds_integrity_and_reviews_missing_human():
    held = build_multimodal_evidence(
        media_type="image",
        cases_evaluated=1,
        integrity_passed=False,
        automatic_metrics_complete=True,
        safety_passed=True,
        held_out_included=True,
        human_review_complete=True,
    )
    assert held["gate_decision"] == "hold"
    assert "artifact integrity failed" in held["hard_failures"]

    review = build_multimodal_evidence(
        media_type="image",
        cases_evaluated=2,
        integrity_passed=True,
        automatic_metrics_complete=True,
        safety_passed=True,
        held_out_included=True,
        human_review_complete=None,
    )
    assert review["gate_decision"] == "review"
    assert "image human preference evidence absent" in review["review_reasons"]


def test_image_multimodal_pass_requires_human_and_wires_into_bundle():
    evidence = build_multimodal_evidence(
        media_type="image",
        cases_evaluated=10,
        integrity_passed=True,
        automatic_metrics_complete=True,
        safety_passed=True,
        held_out_included=True,
        human_review_complete=True,
    )
    assert evidence["passed"] is True
    result = evaluate_evidence_bundle(
        episodes=[
            {
                "episode_id": "e1",
                "split": "held_out",
                "state_verification": {"passed": True},
            }
        ],
        process_quality={"overall_score": 4.0},
        failure_gate={"decision": "pass"},
        performance_evidence={
            "schema_version": "agent-release-evidence/v1",
            "passed": True,
        },
        multimodal_evidence=evidence,
    )
    assert result["decision"] == "pass"
    assert result["evidence"]["multimodal_present"] is True


def test_bundle_holds_on_multimodal_safety_failure():
    evidence = build_multimodal_evidence(
        media_type="image",
        cases_evaluated=1,
        integrity_passed=True,
        automatic_metrics_complete=True,
        safety_passed=False,
        held_out_included=True,
        human_review_complete=True,
    )
    result = evaluate_evidence_bundle(
        episodes=[
            {
                "episode_id": "e1",
                "split": "held_out",
                "state_verification": {"passed": True},
            }
        ],
        multimodal_evidence=evidence,
    )
    assert result["decision"] == "hold"
    assert any("multimodal safety failed" in item for item in result["hard_failures"])


def test_summarize_case_reports_and_video_dimensions():
    report = MultimodalEvaluator(
        [ArtifactIntegrityMetric(), ClipScoreMetric(), SafetyClassifierMetric()]
    ).evaluate(_image_case())
    evidence = summarize_case_reports(
        [report],
        media_type="image",
        human_review_complete=True,
    )
    assert evidence["passed"] is True

    dims = build_video_dimension_scores(
        {
            "clip_frame_cosine_mean": 0.33,
            "temporal_consistency": 0.8,
            "adjacent_frame_mean_abs_change": 4.0,
        },
        {"nsfw_probability_max": 0.01, "passed": True},
    )
    assert dims["complete"] is True
    assert set(dims["dimensions"]) == {
        "prompt_adherence",
        "temporal_consistency",
        "motion_presence",
        "safety",
    }
