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

__all__ = [
    "ArtifactIntegrityMetric",
    "ArtifactRef",
    "CallableMetricAdapter",
    "MetricResult",
    "MultimodalEvaluator",
    "aggregate_human_ratings",
    "metric_catalog",
]
