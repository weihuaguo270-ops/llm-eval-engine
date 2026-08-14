"""面向图片、视频、音频和文档产物的可插拔评测接口。"""

from .evaluator import (
    ArtifactIntegrityMetric,
    ArtifactRef,
    CallableMetricAdapter,
    MetricResult,
    MultimodalEvaluator,
    aggregate_human_ratings,
    metric_catalog,
)
from .image_benchmark import (
    analyze_panel_ratings,
    analyze_blind_ratings,
    artifact_record,
    build_blind_review,
    build_prompt_dataset,
    build_panel_batches,
    completion_gate,
    compare_model_records,
    dataset_manifest,
    panel_review_progress,
)
from .generation import ClipSafetyScorer, DEFAULT_MODELS, LocalDiffusersGenerator
from .video_benchmark import (
    build_video_prompt_dataset,
    video_artifact_record,
    video_completion_gate,
    video_dataset_manifest,
)

__all__ = [
    "ArtifactIntegrityMetric",
    "ArtifactRef",
    "CallableMetricAdapter",
    "MetricResult",
    "MultimodalEvaluator",
    "aggregate_human_ratings",
    "metric_catalog",
    "analyze_blind_ratings",
    "analyze_panel_ratings",
    "artifact_record",
    "build_blind_review",
    "build_prompt_dataset",
    "build_panel_batches",
    "completion_gate",
    "compare_model_records",
    "dataset_manifest",
    "panel_review_progress",
    "ClipSafetyScorer",
    "DEFAULT_MODELS",
    "LocalDiffusersGenerator",
    "build_video_prompt_dataset",
    "video_artifact_record",
    "video_completion_gate",
    "video_dataset_manifest",
]
