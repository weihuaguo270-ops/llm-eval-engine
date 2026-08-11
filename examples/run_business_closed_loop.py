"""离线评测与发布门禁示例。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval_engine.dataset.governance import audit_splits, build_manifest
from eval_engine.multimodal import (
    ArtifactIntegrityMetric,
    CallableMetricAdapter,
    MultimodalEvaluator,
)
from eval_engine.observability.drift import compare_batches, release_decision
from eval_engine.safety.adversarial import default_attack_cases, run_adversarial_suite


def build_demo_report() -> dict[str, Any]:
    """构建固定输入的离线评测报告。"""
    # 1. 数据版本与切分审计
    cases = [
        {
            "id": "dev-tool-1",
            "split": "dev",
            "query": "calculate 17 * 19",
            "expected": {"tool": "calculator", "answer": "323"},
            "human_score": 5,
            "human_score_r2": 5,
        },
        {
            "id": "held-image-1",
            "split": "held_out",
            "query": "generate a red car turning left",
            "expected": {"media_type": "image"},
            "human_score": 4,
            "human_score_r2": 4,
        },
    ]
    manifest = build_manifest(
        "closed-loop-fixture",
        "v1",
        cases,
        source="offline demo fixtures",
        created_at="fixed",
    )
    data_audit = audit_splits(cases)
    data_audit["fingerprint"] = manifest.fingerprint

    # 2. Artifact 契约与指标聚合
    # fixture 分数只用于测试编排，不作为媒体质量结论。
    media_case = {
        "id": "held-image-1",
        "prompt": "generate a red car turning left",
        "output_artifacts": [
            {
                "id": "image-1",
                "media_type": "image",
                "uri": "artifacts/red-car.png",
                "mime_type": "image/png",
                "width": 1024,
                "height": 768,
            }
        ],
        "human_ratings": [
            {"annotator": "r1", "scores": {"prompt_adherence": 4}},
            {"annotator": "r2", "scores": {"prompt_adherence": 4}},
        ],
    }
    fixture_semantic_metric = CallableMetricAdapter(
        "fixture_prompt_adherence",
        lambda case, artifacts: {
            "score": 0.88,
            "note": "offline fixture; replace with calibrated CLIP/VLM adapter",
        },
        threshold=0.80,
        media_types=("image",),
    )
    media_report = MultimodalEvaluator(
        [ArtifactIntegrityMetric(), fixture_semantic_metric]
    ).evaluate(media_case)

    # 3. 安全回归
    def policy_runner(prompt: str) -> dict[str, Any]:
        if "17 * 19" in prompt:
            return {
                "decision": "allow",
                "tool_calls": [{"name": "calculator"}],
                "output": "323",
            }
        return {"decision": "deny", "tool_calls": [], "output": "request blocked"}

    safety_report = run_adversarial_suite(default_attack_cases(), policy_runner)

    # 4. 基线漂移检查
    baseline_records = [
        {"category": "tool", "passed": True, "overall_score": 4.5, "latency_ms": 100, "tokens": 100},
        {"category": "tool", "passed": True, "overall_score": 4.4, "latency_ms": 110, "tokens": 105},
        {"category": "image", "passed": True, "overall_score": 4.2, "latency_ms": 500, "tokens": 180},
        {"category": "image", "passed": True, "overall_score": 4.1, "latency_ms": 520, "tokens": 185},
    ]
    current_records = [
        {"category": "tool", "passed": True, "overall_score": 4.5, "latency_ms": 103, "tokens": 101},
        {"category": "tool", "passed": True, "overall_score": 4.3, "latency_ms": 112, "tokens": 106},
        {"category": "image", "passed": True, "overall_score": 4.2, "latency_ms": 510, "tokens": 182},
        {"category": "image", "passed": True, "overall_score": 4.0, "latency_ms": 530, "tokens": 188},
    ]
    drift_report = compare_batches(baseline_records, current_records)
    # 5. 发布门禁
    judge_calibration = {
        "gate_split": "held_out",
        "by_split": {"held_out": {"sample_size": 53, "kappa": 0.73}},
    }
    gate = release_decision(
        dataset_audit=data_audit,
        drift_report=drift_report,
        safety_report=safety_report,
        judge_calibration=judge_calibration,
    )
    return {
        "dataset_manifest": manifest.to_dict(),
        "dataset_audit": data_audit,
        "multimodal_evaluation": media_report,
        "safety_evaluation": safety_report,
        "batch_drift": drift_report,
        "judge_calibration": judge_calibration,
        "release_decision": gate,
        "evidence_boundary": {
            "media_semantic_metric": "offline fixture adapter",
            "production_claim": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Optional JSON report path")
    args = parser.parse_args()
    report = build_demo_report()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["release_decision"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
