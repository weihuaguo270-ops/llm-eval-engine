"""Paired shadow/A-B experiment analysis for Agent releases."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


def analyze_paired_experiment(
    records: Sequence[Mapping[str, Any]],
    *,
    primary_metric: str = "task_success",
    max_guardrail_regression: float = 0.05,
    z_value: float = 1.96,
) -> dict[str, Any]:
    """Compare baseline and candidate on the same tasks with uncertainty."""
    if not records:
        raise ValueError("paired experiment requires records")
    wins = losses = ties = 0
    guardrail_failures: list[str] = []
    deltas = []
    for row in records:
        baseline = float((row.get("baseline") or {}).get(primary_metric, 0.0))
        candidate = float((row.get("candidate") or {}).get(primary_metric, 0.0))
        delta = candidate - baseline
        deltas.append(delta)
        wins += delta > 0
        losses += delta < 0
        ties += delta == 0
        for metric in ("latency_ms", "cost"):
            old = float((row.get("baseline") or {}).get(metric, 0.0))
            new = float((row.get("candidate") or {}).get(metric, 0.0))
            if old > 0 and (new - old) / old > max_guardrail_regression:
                guardrail_failures.append(f"{row.get('task_id')}:{metric}")

    n = len(deltas)
    mean_delta = sum(deltas) / n
    variance = sum((value - mean_delta) ** 2 for value in deltas) / max(1, n - 1)
    margin = z_value * math.sqrt(variance / n)
    lower, upper = mean_delta - margin, mean_delta + margin
    decision = "hold" if guardrail_failures or upper < 0 else "pass" if lower > 0 else "review"
    return {
        "schema_version": "paired-agent-experiment/v1",
        "primary_metric": primary_metric,
        "sample_size": n,
        "baseline_wins": losses,
        "candidate_wins": wins,
        "ties": ties,
        "mean_delta": round(mean_delta, 6),
        "confidence_interval_95": [round(lower, 6), round(upper, 6)],
        "guardrail_failures": guardrail_failures,
        "decision": decision,
        "evidence_boundary": "Offline paired analysis unless records come from assigned production traffic.",
    }
