"""面向图片、视频、音频和文档产物的可插拔评测接口。

生成侧选型（文生图/文生视频横向榜、CLIP 成对选型、图像 v2 offline_real、视频选型流水线）
已从本包移除；多模态主线为轨迹过程评测（含 generate_video / describe_video）+ 理解侧 VQA。
"""

from .evaluator import (
    ArtifactIntegrityMetric,
    ArtifactRef,
    CallableMetricAdapter,
    MetricResult,
    MultimodalEvaluator,
    aggregate_human_ratings,
    metric_catalog,
)
from .understanding import (
    IMAGE_VQA_CASE_COUNT,
    VIDEO_QA_CASE_COUNT,
    build_held_out_understanding_report,
    build_image_vqa_dataset,
    build_video_qa_dataset,
    evaluate_understanding_predictions,
    image_vqa_dataset_manifest,
    score_understanding_answer,
    understanding_case_to_eval_input,
    understanding_evidence_from_finalize,
    video_qa_dataset_manifest,
)
from .understanding_predictors import (
    DEFAULT_UNDERSTANDING_BENCHMARK_MODELS,
    HuggingFaceVLMUnderstandingPredictor,
    OpenAIVisionUnderstandingPredictor,
    SidecarUnderstandingPredictor,
    build_understanding_predictor,
)
from .tracks import (
    run_multimodal_offline_tracks,
    run_understanding_track,
    understanding_completion_gate,
    understanding_track_gate,
)

__all__ = [
    "ArtifactIntegrityMetric",
    "ArtifactRef",
    "CallableMetricAdapter",
    "MetricResult",
    "MultimodalEvaluator",
    "aggregate_human_ratings",
    "metric_catalog",
    "IMAGE_VQA_CASE_COUNT",
    "VIDEO_QA_CASE_COUNT",
    "build_held_out_understanding_report",
    "build_image_vqa_dataset",
    "build_video_qa_dataset",
    "evaluate_understanding_predictions",
    "image_vqa_dataset_manifest",
    "score_understanding_answer",
    "understanding_case_to_eval_input",
    "understanding_evidence_from_finalize",
    "video_qa_dataset_manifest",
    "DEFAULT_UNDERSTANDING_BENCHMARK_MODELS",
    "HuggingFaceVLMUnderstandingPredictor",
    "OpenAIVisionUnderstandingPredictor",
    "SidecarUnderstandingPredictor",
    "build_understanding_predictor",
    "run_multimodal_offline_tracks",
    "run_understanding_track",
    "understanding_completion_gate",
    "understanding_track_gate",
]
