"""evaluator — 多模态 Artifact 评测

内置指标只检查 URI 和技术元数据；模型指标通过 MetricAdapter 接入。
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

_MEDIA_TYPES = {"image", "video", "audio", "document", "other"}
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


@dataclass(frozen=True)
class ArtifactRef:
    """媒体产物引用。"""

    id: str
    media_type: str
    uri: str
    mime_type: str = ""
    sha256: str = ""
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    frame_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArtifactRef":
        """解析并校验 Artifact。"""
        if "data" in value or "base64" in value:
            raise ValueError("embedded media bytes are not allowed; use an artifact uri")
        artifact = cls(
            id=str(value.get("id", "")).strip(),
            media_type=str(value.get("media_type", "")).strip(),
            uri=str(value.get("uri", "")).strip(),
            mime_type=str(value.get("mime_type", "")).strip(),
            sha256=str(value.get("sha256", "")).strip(),
            width=_optional_int(value.get("width")),
            height=_optional_int(value.get("height")),
            duration_ms=_optional_int(value.get("duration_ms")),
            frame_count=_optional_int(value.get("frame_count")),
            metadata=dict(value.get("metadata") or {}),
        )
        artifact.validate()
        return artifact

    def validate(self) -> None:
        """校验必需字段和元数据范围。"""
        if not self.id:
            raise ValueError("artifact.id must be non-empty")
        if self.media_type not in _MEDIA_TYPES:
            raise ValueError(f"unsupported media_type: {self.media_type!r}")
        if not self.uri:
            raise ValueError("artifact.uri must be non-empty")
        if self.sha256 and not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("artifact.sha256 must contain 64 hexadecimal characters")
        for name in ("width", "height"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"artifact.{name} must be positive")
        for name in ("duration_ms", "frame_count"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"artifact.{name} must be non-negative")


@dataclass(frozen=True)
class MetricResult:
    """单项指标结果。"""

    name: str
    score: float | None
    normalized_score: float | None
    passed: bool | None
    details: dict[str, Any] = field(default_factory=dict)
    skipped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetricAdapter(Protocol):
    """多模态指标协议。"""

    name: str
    weight: float
    threshold: float

    def evaluate(
        self,
        case: Mapping[str, Any],
        artifacts: Sequence[ArtifactRef],
    ) -> MetricResult:
        ...


class ArtifactIntegrityMetric:
    """媒体引用完整性指标。"""

    name = "artifact_integrity"

    def __init__(self, *, threshold: float = 1.0, weight: float = 1.0):
        self.threshold = threshold
        self.weight = weight

    def evaluate(
        self,
        case: Mapping[str, Any],
        artifacts: Sequence[ArtifactRef],
    ) -> MetricResult:
        """计算必需元数据完整率。"""
        if not artifacts:
            return MetricResult(
                name=self.name,
                score=None,
                normalized_score=None,
                passed=None,
                skipped_reason="no output artifacts",
            )
        findings: list[dict[str, Any]] = []
        valid = 0
        for artifact in artifacts:
            missing: list[str] = []
            if artifact.media_type == "image":
                if artifact.width is None:
                    missing.append("width")
                if artifact.height is None:
                    missing.append("height")
            elif artifact.media_type == "video":
                if artifact.duration_ms is None:
                    missing.append("duration_ms")
                if artifact.frame_count is None:
                    missing.append("frame_count")
            elif artifact.media_type == "audio" and artifact.duration_ms is None:
                missing.append("duration_ms")
            if not missing:
                valid += 1
            findings.append({"artifact_id": artifact.id, "missing_metadata": missing})
        score = valid / len(artifacts)
        return MetricResult(
            name=self.name,
            score=round(score, 4),
            normalized_score=round(score, 4),
            passed=score >= self.threshold,
            details={"artifacts": findings},
        )


class CallableMetricAdapter:
    """函数式指标适配器。"""

    def __init__(
        self,
        name: str,
        scorer: Callable[[Mapping[str, Any], Sequence[ArtifactRef]], float | Mapping[str, Any]],
        *,
        threshold: float,
        weight: float = 1.0,
        media_types: Sequence[str] = (),
        higher_is_better: bool = True,
        score_range: tuple[float, float] = (0.0, 1.0),
    ):
        self.name = name
        self.scorer = scorer
        self.threshold = threshold
        self.weight = weight
        self.media_types = set(media_types)
        self.higher_is_better = higher_is_better
        self.score_range = (float(score_range[0]), float(score_range[1]))
        if self.score_range[1] <= self.score_range[0]:
            raise ValueError("score_range maximum must be greater than minimum")

    def evaluate(
        self,
        case: Mapping[str, Any],
        artifacts: Sequence[ArtifactRef],
    ) -> MetricResult:
        """执行指标并统一输出格式。"""
        selected = [
            artifact for artifact in artifacts
            if not self.media_types or artifact.media_type in self.media_types
        ]
        if not selected:
            return MetricResult(
                name=self.name,
                score=None,
                normalized_score=None,
                passed=None,
                skipped_reason="no compatible artifacts",
            )
        raw = self.scorer(case, selected)
        if isinstance(raw, Mapping):
            if "score" not in raw:
                raise ValueError(f"metric {self.name!r} result is missing score")
            score = float(raw["score"])
            explicit_normalized = raw.get("normalized_score")
            details = {
                key: value
                for key, value in raw.items()
                if key not in {"score", "normalized_score"}
            }
        else:
            score = float(raw)
            explicit_normalized = None
            details = {}
        if not math.isfinite(score):
            raise ValueError(f"metric {self.name!r} returned a non-finite score")
        # 统一为 0-1 且越大越好，便于跨指标聚合。
        if explicit_normalized is None:
            low, high = self.score_range
            normalized = (score - low) / (high - low)
            if not self.higher_is_better:
                normalized = 1.0 - normalized
        else:
            normalized = float(explicit_normalized)
        normalized = min(1.0, max(0.0, normalized))
        passed = (
            score >= self.threshold
            if self.higher_is_better
            else score <= self.threshold
        )
        details["higher_is_better"] = self.higher_is_better
        details["score_range"] = list(self.score_range)
        return MetricResult(
            name=self.name,
            score=score,
            normalized_score=round(normalized, 4),
            passed=passed,
            details=details,
        )


class MultimodalEvaluator:
    """单条样本的多模态指标编排器。"""

    def __init__(self, metrics: Sequence[MetricAdapter] | None = None):
        self.metrics = list(metrics or [ArtifactIntegrityMetric()])

    def evaluate(self, case: Mapping[str, Any]) -> dict[str, Any]:
        """评测 output_artifacts。"""
        raw_artifacts = case.get("output_artifacts") or case.get("artifacts") or []
        if not isinstance(raw_artifacts, list):
            raise ValueError("output_artifacts must be an array")
        artifacts = [ArtifactRef.from_dict(value) for value in raw_artifacts]
        results = [metric.evaluate(case, artifacts) for metric in self.metrics]

        # 不同指标量纲不同，只聚合 normalized_score。
        weighted_score = 0.0
        weight_sum = 0.0
        for metric, result in zip(self.metrics, results):
            if result.normalized_score is None:
                continue
            weighted_score += float(result.normalized_score) * float(metric.weight)
            weight_sum += float(metric.weight)
        overall = round(weighted_score / weight_sum, 4) if weight_sum else None
        failed = [result.name for result in results if result.passed is False]
        evaluated = [result for result in results if result.score is not None]
        return {
            "case_id": str(case.get("id", "")),
            "prompt": str(case.get("prompt", case.get("query", ""))),
            "artifact_count": len(artifacts),
            "media_types": sorted({artifact.media_type for artifact in artifacts}),
            "overall_score": overall,
            "passed": not failed and bool(evaluated),
            "failed_metrics": failed,
            "metrics": [result.to_dict() for result in results],
            "human_ratings": aggregate_human_ratings(case.get("human_ratings") or []),
        }


def aggregate_human_ratings(
    ratings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """按维度汇总 1-5 分人工评分。"""
    by_dimension: dict[str, list[float]] = {}
    for rating in ratings:
        scores = rating.get("scores") or {}
        if not isinstance(scores, Mapping):
            raise ValueError("human rating scores must be an object")
        for dimension, raw_score in scores.items():
            score = float(raw_score)
            if not 1.0 <= score <= 5.0:
                raise ValueError("human ratings must use the 1-5 scale")
            by_dimension.setdefault(str(dimension), []).append(score)

    dimensions: dict[str, dict[str, Any]] = {}
    for dimension, scores in sorted(by_dimension.items()):
        mean = sum(scores) / len(scores)
        variance = sum((score - mean) ** 2 for score in scores) / len(scores)
        dimensions[dimension] = {
            "sample_size": len(scores),
            "mean": round(mean, 4),
            "normalized_mean": round(mean / 5.0, 4),
            "stddev": round(math.sqrt(variance), 4),
        }
    return {"rater_count": len(ratings), "dimensions": dimensions}


def metric_catalog() -> list[dict[str, str]]:
    """返回内置指标和待接入适配器清单。"""
    return [
        {"name": "artifact_integrity", "scope": "per-artifact metadata", "status": "built_in"},
        {"name": "human_ratings", "scope": "rubric aggregation", "status": "built_in"},
        {"name": "CLIPScore/SigLIP", "scope": "prompt adherence", "status": "adapter_required"},
        {"name": "ImageReward/HPS", "scope": "image preference", "status": "adapter_required"},
        {"name": "FID/KID", "scope": "dataset distribution", "status": "adapter_required"},
        {"name": "LPIPS", "scope": "perceptual similarity", "status": "adapter_required"},
        {"name": "FVD/VBench", "scope": "video quality and consistency", "status": "adapter_required"},
        {"name": "VLM Judge", "scope": "semantic rubric", "status": "calibrated_adapter_required"},
        {"name": "safety classifier", "scope": "content policy", "status": "adapter_required"},
    ]


def _optional_int(value: Any) -> int | None:
    """解析可选整数元数据。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid integer metadata value")
    return int(value)
