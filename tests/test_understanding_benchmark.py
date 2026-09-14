"""Contracts for understanding-side image/video QA datasets."""

from eval_engine.multimodal import (
    IMAGE_VQA_CASE_COUNT,
    VIDEO_QA_CASE_COUNT,
    MultimodalEvaluator,
    build_image_vqa_dataset,
    build_video_qa_dataset,
    evaluate_understanding_predictions,
    image_vqa_dataset_manifest,
    metric_catalog,
    score_understanding_answer,
    understanding_case_to_eval_input,
    video_qa_dataset_manifest,
)


def test_image_vqa_dataset_is_frozen_and_split_isolated():
    cases = build_image_vqa_dataset()
    manifest = image_vqa_dataset_manifest(cases)
    assert len(cases) == IMAGE_VQA_CASE_COUNT == 40
    assert manifest["split_counts"] == {"dev": 8, "golden": 20, "held_out": 12}
    assert manifest["fingerprint_sha256"]
    assert all(case["task_type"] == "image_vqa" for case in cases)
    assert all(case["media_status"] == "reference_only" for case in cases)


def test_video_qa_dataset_is_frozen_and_split_isolated():
    cases = build_video_qa_dataset()
    manifest = video_qa_dataset_manifest(cases)
    assert len(cases) == VIDEO_QA_CASE_COUNT == 30
    assert manifest["split_counts"] == {"dev": 8, "golden": 14, "held_out": 8}
    assert all(case["task_type"] == "video_qa" for case in cases)
    assert "Video-MME" in " ".join(manifest["peer_suites"])


def test_score_understanding_answer_supports_exact_short_and_mcq():
    image_cases = build_image_vqa_dataset()
    short = next(case for case in image_cases if case["answer_type"] == "short")
    exact = next(case for case in image_cases if case["answer_type"] == "exact")
    mcq = next(case for case in image_cases if case["answer_type"] == "mcq")

    assert score_understanding_answer(short, short["answer"].upper())["passed"] is True
    assert score_understanding_answer(exact, "999")["passed"] is False
    assert score_understanding_answer(exact, exact["answer"])["passed"] is True
    assert score_understanding_answer(mcq, "A")["passed"] is True
    assert score_understanding_answer(mcq, "wrong")["passed"] is False
    assert score_understanding_answer(short, "")["reason"] == "empty_prediction"


def test_evaluate_understanding_predictions_reports_accuracy():
    cases = build_image_vqa_dataset()[:5]
    predictions = {case["id"]: case["answer"] for case in cases}
    predictions[cases[0]["id"]] = "definitely-wrong"
    report = evaluate_understanding_predictions(cases, predictions)
    assert report["scored_count"] == 5
    assert report["overall_accuracy"] == 0.8
    assert report["missing_predictions"] == []


def test_understanding_case_projects_into_multimodal_evaluator():
    case = understanding_case_to_eval_input(build_video_qa_dataset()[0])
    report = MultimodalEvaluator().evaluate(case)
    assert report["media_types"] == ["video"]
    assert report["passed"] is True


def test_metric_catalog_lists_understanding_accuracy():
    catalog = {item["name"]: item["status"] for item in metric_catalog()}
    assert catalog["image_vqa_accuracy"] == "built_in"
    assert catalog["video_qa_accuracy"] == "built_in"
