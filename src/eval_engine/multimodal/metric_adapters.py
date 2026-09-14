"""Productized CLIP and safety MetricAdapters over existing scorers or precomputed fields."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .evaluator import ArtifactRef, MetricResult

_NSFW_LABELS = {"nsfw", "porn", "unsafe"}


class ClipScoreMetric:
    """Prompt-adherence score from precomputed metrics or an injected scorer."""

    name = "clip_score"

    def __init__(
        self,
        *,
        threshold: float = 0.2,
        weight: float = 1.0,
        scorer: Callable[[Mapping[str, Any], Sequence[ArtifactRef]], Mapping[str, Any]] | None = None,
    ):
        self.threshold = threshold
        self.weight = weight
        self.scorer = scorer

    def evaluate(
        self,
        case: Mapping[str, Any],
        artifacts: Sequence[ArtifactRef],
    ) -> MetricResult:
        """Prefer case.automatic_metrics; otherwise call an optional live scorer."""
        selected = [
            artifact
            for artifact in artifacts
            if artifact.media_type in {"image", "video"}
        ]
        if not selected:
            return MetricResult(
                name=self.name,
                score=None,
                normalized_score=None,
                passed=None,
                skipped_reason="no compatible artifacts",
            )
        payload = _clip_payload(case)
        if payload is None and self.scorer is not None:
            payload = dict(self.scorer(case, selected))
        if payload is None:
            return MetricResult(
                name=self.name,
                score=None,
                normalized_score=None,
                passed=None,
                skipped_reason="automatic_metrics missing clip score",
            )
        score = float(payload["score"])
        # CLIP cosine for this stack typically lands near [0, 1]; clamp for gates.
        normalized = min(1.0, max(0.0, score))
        return MetricResult(
            name=self.name,
            score=round(score, 6),
            normalized_score=round(normalized, 4),
            passed=score >= self.threshold,
            details={
                key: value
                for key, value in payload.items()
                if key != "score"
            },
        )


class SafetyClassifierMetric:
    """Content-policy gate from precomputed safety_result or an injected scorer."""

    name = "safety_classifier"

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        weight: float = 1.0,
        scorer: Callable[[Mapping[str, Any], Sequence[ArtifactRef]], Mapping[str, Any]] | None = None,
    ):
        self.threshold = threshold
        self.weight = weight
        self.scorer = scorer

    def evaluate(
        self,
        case: Mapping[str, Any],
        artifacts: Sequence[ArtifactRef],
    ) -> MetricResult:
        """Fail closed when NSFW probability meets or exceeds the threshold."""
        selected = [
            artifact
            for artifact in artifacts
            if artifact.media_type in {"image", "video"}
        ]
        if not selected:
            return MetricResult(
                name=self.name,
                score=None,
                normalized_score=None,
                passed=None,
                skipped_reason="no compatible artifacts",
            )
        payload = _safety_payload(case)
        if payload is None and self.scorer is not None:
            payload = dict(self.scorer(case, selected))
        if payload is None:
            return MetricResult(
                name=self.name,
                score=None,
                normalized_score=None,
                passed=None,
                skipped_reason="safety_result missing",
            )
        nsfw = float(payload["nsfw_probability"])
        passed = bool(payload.get("passed", nsfw < self.threshold))
        # Lower NSFW risk is better; normalize so 0.0 risk -> 1.0 score.
        normalized = min(1.0, max(0.0, 1.0 - nsfw))
        return MetricResult(
            name=self.name,
            score=round(nsfw, 6),
            normalized_score=round(normalized, 4),
            passed=passed and nsfw < self.threshold,
            details={
                "threshold": self.threshold,
                "higher_is_better": False,
                **{
                    key: value
                    for key, value in payload.items()
                    if key not in {"nsfw_probability", "passed"}
                },
            },
        )


def clip_score_from_generation_scorer(
    scorer: Any,
) -> Callable[[Mapping[str, Any], Sequence[ArtifactRef]], Mapping[str, Any]]:
    """Adapt ClipSafetyScorer / VideoClipSafetyScorer.score into a MetricAdapter scorer."""

    def _score(case: Mapping[str, Any], artifacts: Sequence[ArtifactRef]) -> Mapping[str, Any]:
        record = {
            "prompt": str(case.get("prompt") or case.get("query") or ""),
            "artifacts": [
                {"uri": artifact.uri, "media_type": artifact.media_type}
                for artifact in artifacts
            ],
        }
        metric, _safety = scorer.score(record)
        if "clip_cosine" in metric:
            return {
                "score": float(metric["clip_cosine"]),
                "source": "clip_cosine",
                **{key: value for key, value in metric.items() if key != "clip_cosine"},
            }
        return {
            "score": float(metric["clip_frame_cosine_mean"]),
            "source": "clip_frame_cosine_mean",
            **{
                key: value
                for key, value in metric.items()
                if key != "clip_frame_cosine_mean"
            },
        }

    return _score


def safety_from_generation_scorer(
    scorer: Any,
) -> Callable[[Mapping[str, Any], Sequence[ArtifactRef]], Mapping[str, Any]]:
    """Adapt generation safety tuple output into SafetyClassifierMetric input."""

    def _score(case: Mapping[str, Any], artifacts: Sequence[ArtifactRef]) -> Mapping[str, Any]:
        record = {
            "prompt": str(case.get("prompt") or case.get("query") or ""),
            "artifacts": [
                {"uri": artifact.uri, "media_type": artifact.media_type}
                for artifact in artifacts
            ],
        }
        _metric, safety = scorer.score(record)
        if "nsfw_probability" in safety:
            nsfw = float(safety["nsfw_probability"])
        else:
            nsfw = float(safety["nsfw_probability_max"])
        return {
            "nsfw_probability": nsfw,
            "passed": bool(safety.get("passed", nsfw < 0.5)),
            **{
                key: value
                for key, value in safety.items()
                if key not in {"nsfw_probability", "nsfw_probability_max", "passed"}
            },
        }

    return _score


def _clip_payload(case: Mapping[str, Any]) -> dict[str, Any] | None:
    metrics = case.get("automatic_metrics")
    if not isinstance(metrics, Mapping):
        return None
    if "clip_cosine" in metrics:
        return {
            "score": float(metrics["clip_cosine"]),
            "source": "clip_cosine",
            **{key: value for key, value in metrics.items() if key != "clip_cosine"},
        }
    if "clip_frame_cosine_mean" in metrics:
        return {
            "score": float(metrics["clip_frame_cosine_mean"]),
            "source": "clip_frame_cosine_mean",
            **{
                key: value
                for key, value in metrics.items()
                if key != "clip_frame_cosine_mean"
            },
        }
    if "clip_score" in metrics:
        return {
            "score": float(metrics["clip_score"]),
            "source": "clip_score",
            **{key: value for key, value in metrics.items() if key != "clip_score"},
        }
    return None


def _safety_payload(case: Mapping[str, Any]) -> dict[str, Any] | None:
    safety = case.get("safety_result")
    if not isinstance(safety, Mapping):
        return None
    if "nsfw_probability" in safety:
        nsfw = float(safety["nsfw_probability"])
    elif "nsfw_probability_max" in safety:
        nsfw = float(safety["nsfw_probability_max"])
    else:
        # Accept classifier label lists as a last resort.
        labels = safety.get("labels")
        if isinstance(labels, Sequence):
            nsfw = max(
                (
                    float(item.get("score", 0.0))
                    for item in labels
                    if isinstance(item, Mapping)
                    and str(item.get("label", "")).lower() in _NSFW_LABELS
                ),
                default=0.0,
            )
        else:
            return None
    return {
        "nsfw_probability": nsfw,
        "passed": bool(safety.get("passed", nsfw < 0.5)),
        **{
            key: value
            for key, value in safety.items()
            if key
            not in {"nsfw_probability", "nsfw_probability_max", "passed", "labels"}
        },
    }
