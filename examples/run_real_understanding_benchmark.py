"""Staged real understanding benchmark: init → materialize → predict → score → finalize.

Mirrors generation-side ``run_real_image/video_benchmark.py`` for understanding
(image VQA + video QA).

Default predictors are local sidecar readers (offline wiring). Use real models via:
  --adapter sidecar-reader=openai_vision
  --adapter noisy-sidecar-reader=hf_vlm

Usage:
  PYTHONPATH=src python examples/run_real_understanding_benchmark.py init --output /tmp/u
  PYTHONPATH=src python examples/run_real_understanding_benchmark.py materialize --output /tmp/u
  PYTHONPATH=src python examples/run_real_understanding_benchmark.py predict --output /tmp/u
  PYTHONPATH=src python examples/run_real_understanding_benchmark.py score --output /tmp/u
  PYTHONPATH=src python examples/run_real_understanding_benchmark.py finalize --output /tmp/u
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.multimodal.synthetic_media import materialize_understanding_case  # noqa: E402
from eval_engine.multimodal.tracks import (  # noqa: E402
    understanding_completion_gate,
    understanding_track_gate,
)
from eval_engine.multimodal.understanding import (  # noqa: E402
    build_held_out_understanding_report,
    build_image_vqa_dataset,
    build_video_qa_dataset,
    evaluate_understanding_predictions,
    image_vqa_dataset_manifest,
    score_understanding_answer,
    understanding_evidence_from_finalize,
    video_qa_dataset_manifest,
)
from eval_engine.multimodal.understanding_predictors import (  # noqa: E402
    DEFAULT_UNDERSTANDING_BENCHMARK_MODELS,
    build_understanding_predictor,
)


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _smoke_slice(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    held = next(case for case in cases if case["split"] == "held_out")
    return [cases[0], held]


def initialize(output: Path) -> dict:
    image_cases = build_image_vqa_dataset()
    video_cases = build_video_qa_dataset()
    payload = {
        "schema_version": "real-understanding-benchmark-dataset/v1",
        "image_dataset": image_vqa_dataset_manifest(image_cases),
        "video_dataset": video_qa_dataset_manifest(video_cases),
        "image_cases": image_cases,
        "video_cases": video_cases,
        "models": [dict(model) for model in DEFAULT_UNDERSTANDING_BENCHMARK_MODELS],
        "claim_boundary": (
            "Dataset contracts only until materialize/predict/score/finalize pass "
            "the understanding offline_real gate."
        ),
    }
    write_json(output / "dataset.json", payload)
    return payload


def materialize(output: Path, smoke: bool = False) -> dict:
    source = read_json(output / "dataset.json", None) or initialize(output)
    image_cases = list(source["image_cases"])
    video_cases = list(source["video_cases"])
    if smoke:
        image_cases = _smoke_slice(image_cases)
        video_cases = _smoke_slice(video_cases)
    media_root = output / "artifacts" / "media"
    image_materialized = [
        materialize_understanding_case(case, media_root) for case in image_cases
    ]
    video_materialized = [
        materialize_understanding_case(case, media_root) for case in video_cases
    ]
    payload = {
        "schema_version": "real-understanding-materialized/v1",
        "smoke": smoke,
        "image_cases": image_materialized,
        "video_cases": video_materialized,
        "models": source["models"],
        "image_real_media": all(
            Path(str(case["artifact"]["uri"])).is_file() for case in image_materialized
        ),
        "video_real_media": all(
            Path(str(case["artifact"]["uri"])).is_file() for case in video_materialized
        ),
    }
    write_json(output / ("smoke_materialized.json" if smoke else "materialized.json"), payload)
    return {
        "image_cases": len(image_materialized),
        "video_cases": len(video_materialized),
        "image_real_media": payload["image_real_media"],
        "video_real_media": payload["video_real_media"],
    }


def _load_materialized(output: Path, smoke: bool) -> dict:
    path = output / ("smoke_materialized.json" if smoke else "materialized.json")
    payload = read_json(path, None)
    if payload is None:
        materialize(output, smoke=smoke)
        payload = read_json(path, None)
    if not payload:
        raise ValueError("materialized cases are required before predict")
    return payload


def predict(
    output: Path,
    smoke: bool = False,
    *,
    adapter_overrides: dict[str, str] | None = None,
) -> dict:
    source = _load_materialized(output, smoke)
    target = output / ("smoke_prediction_records.json" if smoke else "prediction_records.json")
    records = read_json(target, [])
    completed = {(row["case_id"], row["model"]) for row in records}
    overrides = adapter_overrides or {}
    predictors = {}
    for model in source["models"]:
        adapter = (
            overrides.get(model["id"])
            or overrides.get(model["alias"])
            or model["adapter"]
        )
        predictors[model["id"]] = build_understanding_predictor(
            adapter=adapter,
            model_id=model["id"],
        )
    for model in source["models"]:
        predictor = predictors[model["id"]]
        for case in list(source["image_cases"]) + list(source["video_cases"]):
            key = (case["id"], model["id"])
            if key in completed:
                continue
            result = predictor.predict(case)
            records.append(
                {
                    "case_id": case["id"],
                    "split": case["split"],
                    "task_type": case["task_type"],
                    "category": case["category"],
                    "question": case["question"],
                    "model": model["id"],
                    "adapter": result.get("adapter") or model["adapter"],
                    "prediction": result["prediction"],
                    "latency_ms": result.get("latency_ms"),
                    "model_revision": result.get("model_revision"),
                    "artifact": case["artifact"],
                    "claim_boundary": result.get("claim_boundary"),
                }
            )
            write_json(target, records)
            completed.add(key)
    return {
        "records": len(records),
        "models": sorted({row["model"] for row in records}),
        "adapters": sorted({str(row.get("adapter")) for row in records}),
    }


def score(output: Path, smoke: bool = False) -> dict:
    materialized = _load_materialized(output, smoke)
    target = output / ("smoke_prediction_records.json" if smoke else "prediction_records.json")
    records = read_json(target, [])
    if not records:
        raise ValueError("prediction records are required before scoring")
    cases = {
        str(case["id"]): case
        for case in list(materialized["image_cases"]) + list(materialized["video_cases"])
    }
    for record in records:
        if record.get("automatic_metrics"):
            continue
        case = cases[str(record["case_id"])]
        scored = score_understanding_answer(case, record.get("prediction"))
        record["automatic_metrics"] = {
            "accuracy": scored["score"],
            "matched": scored["matched"],
            "reason": scored["reason"],
        }
        record["score"] = scored
        write_json(target, records)
    return {
        "records": len(records),
        "scored": sum(bool(row.get("automatic_metrics")) for row in records),
        "mean_accuracy": round(
            sum(
                float((row.get("automatic_metrics") or {}).get("accuracy") or 0.0)
                for row in records
            )
            / max(len(records), 1),
            4,
        ),
    }


def finalize(output: Path, smoke: bool = False) -> dict:
    materialized = _load_materialized(output, smoke)
    records = read_json(
        output / ("smoke_prediction_records.json" if smoke else "prediction_records.json"),
        [],
    )
    if not records:
        raise ValueError("scored prediction records are required before finalize")
    image_cases = materialized["image_cases"]
    video_cases = materialized["video_cases"]
    image_records = [row for row in records if row.get("task_type") == "image_vqa"]
    video_records = [row for row in records if row.get("task_type") == "video_qa"]
    track_gate = understanding_track_gate(
        image_records=image_records,
        video_records=video_records,
        expected_image_cases=len(image_cases),
        expected_video_cases=len(video_cases),
    )
    primary_model = str(materialized["models"][0]["id"])
    image_predictions = {
        row["case_id"]: row["prediction"]
        for row in image_records
        if row["model"] == primary_model
    }
    video_predictions = {
        row["case_id"]: row["prediction"]
        for row in video_records
        if row["model"] == primary_model
    }
    image_full = evaluate_understanding_predictions(image_cases, image_predictions)
    video_full = evaluate_understanding_predictions(video_cases, video_predictions)
    image_held = build_held_out_understanding_report(
        image_cases,
        image_predictions,
        model_id=primary_model,
        modality="image_vqa",
    )
    video_held = build_held_out_understanding_report(
        video_cases,
        video_predictions,
        model_id=primary_model,
        modality="video_qa",
    )
    predictor_claim = str(
        next(
            (
                row.get("claim_boundary")
                for row in records
                if row.get("model") == primary_model and row.get("claim_boundary")
            ),
            track_gate.get("claim_boundary"),
        )
    )
    evidence = understanding_evidence_from_finalize(
        track_gate=track_gate,
        image_held_out=image_held,
        video_held_out=video_held,
        predictor_claim=predictor_claim,
    )
    dataset = read_json(output / "dataset.json", {})
    dataset_audit = {
        "passed": bool(
            track_gate.get("passed")
            and image_held.get("passed")
            and video_held.get("passed")
        ),
        "image_manifest": dataset.get("image_dataset")
        or image_vqa_dataset_manifest(image_cases),
        "video_manifest": dataset.get("video_dataset")
        or video_qa_dataset_manifest(video_cases),
        "held_out_image_cases": image_held.get("held_out_case_count"),
        "held_out_video_cases": video_held.get("held_out_case_count"),
        "source": "real-understanding-benchmark",
    }
    report = {
        "schema_version": "real-understanding-benchmark-report/v1",
        "smoke": smoke,
        "records": len(records),
        "primary_model": primary_model,
        "image_completion_gate": understanding_completion_gate(
            image_records, expected_cases=len(image_cases)
        ),
        "video_completion_gate": understanding_completion_gate(
            video_records, expected_cases=len(video_cases)
        ),
        "track_gate": track_gate,
        "primary_image_report": image_full,
        "primary_video_report": video_full,
        "held_out_image_report": image_held,
        "held_out_video_report": video_held,
        "multimodal_understanding_evidence": evidence,
        "dataset_audit": dataset_audit,
        "claim_boundary": predictor_claim,
    }
    write_json(output / ("smoke_report.json" if smoke else "final_report.json"), report)
    write_json(
        output
        / (
            "smoke_multimodal_understanding_evidence.json"
            if smoke
            else "multimodal_understanding_evidence.json"
        ),
        evidence,
    )
    write_json(
        output / ("smoke_dataset_audit.json" if smoke else "dataset_audit.json"),
        dataset_audit,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("init", "materialize", "predict", "score", "finalize"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--adapter",
        action="append",
        default=[],
        help="Override adapter as model_id=adapter or alias=adapter. Repeatable.",
    )
    args = parser.parse_args()
    overrides: dict[str, str] = {}
    for item in args.adapter:
        if "=" not in item:
            raise SystemExit(f"--adapter expects model=adapter, got {item!r}")
        key, value = item.split("=", 1)
        overrides[key.strip()] = value.strip()

    if args.command == "init":
        result = initialize(args.output)
        result = {
            "image_dataset": result["image_dataset"],
            "video_dataset": result["video_dataset"],
            "models": result["models"],
        }
    elif args.command == "materialize":
        result = materialize(args.output, smoke=args.smoke)
    elif args.command == "predict":
        result = predict(args.output, smoke=args.smoke, adapter_overrides=overrides)
    elif args.command == "score":
        result = score(args.output, smoke=args.smoke)
    else:
        result = finalize(args.output, smoke=args.smoke)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "finalize":
        return 0 if result.get("track_gate", {}).get("passed") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
