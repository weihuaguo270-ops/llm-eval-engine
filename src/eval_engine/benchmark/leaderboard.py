"""Cross-benchmark model comparison without averaging raw incompatible scores."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Mapping, Sequence


def analyze_leaderboards(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build percentile ranks, uncertainty-aware leaders, correlation, and Pareto sets."""
    if not records:
        raise ValueError("leaderboard records are required")
    by_benchmark: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        by_benchmark[str(row["benchmark"])].append(row)

    normalized: list[dict[str, Any]] = []
    for benchmark, rows in sorted(by_benchmark.items()):
        ordered = sorted(rows, key=lambda row: float(row["score"]))
        count = len(ordered)
        for rank, row in enumerate(ordered, 1):
            normalized.append({
                **dict(row),
                "percentile": 1.0 if count == 1 else round((rank - 1) / (count - 1), 6),
            })

    models = sorted({str(row["model_version"]) for row in normalized})
    aggregate = []
    for model in models:
        rows = [row for row in normalized if row["model_version"] == model]
        aggregate.append({
            "model_version": model,
            "benchmarks": len(rows),
            "mean_percentile": round(sum(row["percentile"] for row in rows) / len(rows), 6),
            "mean_cost": round(sum(float(row.get("cost", 0.0)) for row in rows) / len(rows), 6),
            "mean_latency_ms": round(sum(float(row.get("latency", 0.0)) for row in rows) / len(rows), 3),
        })

    correlations = {}
    names = sorted(by_benchmark)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1:]:
            left_scores = {str(row["model_version"]): float(row["score"]) for row in by_benchmark[left]}
            right_scores = {str(row["model_version"]): float(row["score"]) for row in by_benchmark[right]}
            shared = sorted(set(left_scores) & set(right_scores))
            correlations[f"{left}|{right}"] = _pearson(
                [left_scores[name] for name in shared], [right_scores[name] for name in shared]
            ) if len(shared) >= 2 else None

    pareto = [row["model_version"] for row in aggregate if not any(
        other["mean_percentile"] >= row["mean_percentile"]
        and other["mean_cost"] <= row["mean_cost"]
        and other["mean_latency_ms"] <= row["mean_latency_ms"]
        and other != row for other in aggregate)]
    return {"schema_version": "multi-leaderboard-analysis/v1", "benchmarks": names,
            "normalized_records": normalized, "aggregate": aggregate,
            "benchmark_correlations": correlations, "pareto_models": pareto,
            "warning": "A mean percentile is descriptive, not proof of a universally best model."}


def _pearson(left: list[float], right: list[float]) -> float | None:
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_var = sum((x - left_mean) ** 2 for x in left)
    right_var = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_var * right_var)
    return round(numerator / denominator, 6) if denominator else None


def analyze_paired_leaderboard(records: Sequence[Mapping[str, Any]], *, metric: str,
                               higher_is_better: bool = True, seed: int = 20260813,
                               bootstrap_samples: int = 2000) -> dict[str, Any]:
    """Rank models on one frozen paired benchmark with uncertainty and guardrails."""
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in records:
        by_case[str(row["case_id"])][str(row["model"])] = row
    models = sorted({str(row["model"]) for row in records})
    if len(models) != 2:
        raise ValueError("paired leaderboard requires exactly two models")
    pairs = [pair for pair in by_case.values() if set(pair) == set(models)]
    if not pairs:
        raise ValueError("paired leaderboard requires shared cases")

    rng = random.Random(seed)
    summaries = []
    for model in models:
        rows = [pair[model] for pair in pairs]
        scores = [_metric_value(row, metric) for row in rows]
        means = sorted(sum(rng.choice(scores) for _ in scores) / len(scores)
                       for _ in range(bootstrap_samples))
        latencies = sorted(float(row.get("latency_ms", 0.0)) for row in rows)
        summaries.append({"model": model, "model_versions": sorted({str(row.get("model_version", "")) for row in rows}),
                          "samples": len(rows), "mean_score": round(sum(scores) / len(scores), 6),
                          "score_bootstrap_95_ci": [_quantile(means, 0.025), _quantile(means, 0.975)],
                          "mean_latency_ms": round(sum(latencies) / len(latencies), 3),
                          "p95_latency_ms": round(latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)], 3),
                          "safety_pass_rate": round(sum(bool((row.get("safety_result") or {}).get("passed"))
                                                        for row in rows) / len(rows), 4),
                          "held_out_mean_score": _slice_mean(rows, metric, "held_out")})

    left, right = models
    deltas = [_metric_value(pair[left], metric) - _metric_value(pair[right], metric) for pair in pairs]
    delta_means = sorted(sum(rng.choice(deltas) for _ in deltas) / len(deltas)
                         for _ in range(bootstrap_samples))
    ordered = sorted(summaries, key=lambda row: row["mean_score"], reverse=higher_is_better)
    statistically_separated = not (_quantile(delta_means, 0.025) <= 0 <= _quantile(delta_means, 0.975))
    return {"schema_version": "paired-real-leaderboard/v1", "metric": metric,
            "higher_is_better": higher_is_better, "paired_cases": len(pairs),
            "ranking": ordered, "leader": ordered[0]["model"],
            "mean_difference_left_minus_right": round(sum(deltas) / len(deltas), 6),
            "difference_bootstrap_95_ci": [_quantile(delta_means, 0.025), _quantile(delta_means, 0.975)],
            "statistically_separated": statistically_separated,
            "left_wins": sum(delta > 0 for delta in deltas),
            "right_wins": sum(delta < 0 for delta in deltas), "ties": sum(delta == 0 for delta in deltas),
            "claim_boundary": "Ranking applies only to this frozen dataset, metric, model revision and generation configuration."}


def _metric_value(row: Mapping[str, Any], metric: str) -> float:
    value: Any = row
    for part in metric.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ValueError(f"record is missing metric {metric}: {row.get('case_id')}")
        value = value[part]
    return float(value)


def _slice_mean(rows: Sequence[Mapping[str, Any]], metric: str, split: str) -> float | None:
    values = [_metric_value(row, metric) for row in rows if row.get("split") == split]
    return round(sum(values) / len(values), 6) if values else None


def _quantile(values: Sequence[float], fraction: float) -> float:
    index = min(len(values) - 1, max(0, int(len(values) * fraction)))
    return round(float(values[index]), 6)
