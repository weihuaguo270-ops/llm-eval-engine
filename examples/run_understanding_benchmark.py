"""Export understanding-side image/video QA datasets and score fixture answers.

Usage:
  PYTHONPATH=src python examples/run_understanding_benchmark.py
  PYTHONPATH=src python examples/run_understanding_benchmark.py --out /tmp/understanding
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_engine.multimodal import (
    build_image_vqa_dataset,
    build_video_qa_dataset,
    evaluate_understanding_predictions,
    image_vqa_dataset_manifest,
    video_qa_dataset_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/understanding-benchmark"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    image_cases = build_image_vqa_dataset()
    video_cases = build_video_qa_dataset()
    image_manifest = image_vqa_dataset_manifest(image_cases)
    video_manifest = video_qa_dataset_manifest(video_cases)

    # Offline smoke path: gold answers as predictions prove the scorer wiring.
    image_report = evaluate_understanding_predictions(
        image_cases,
        {case["id"]: case["answer"] for case in image_cases},
    )
    video_report = evaluate_understanding_predictions(
        video_cases,
        {case["id"]: case["answer"] for case in video_cases},
    )
    payload = {
        "image_vqa": {"manifest": image_manifest, "cases": image_cases, "oracle_report": image_report},
        "video_qa": {"manifest": video_manifest, "cases": video_cases, "oracle_report": video_report},
        "claim_boundary": (
            "Dataset contracts and offline scorers only. Media URIs are references; "
            "live VLM scoring requires attaching real image/video files."
        ),
    }
    target = args.out / "understanding_benchmark.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "image_cases": image_manifest["case_count"],
                "video_cases": video_manifest["case_count"],
                "image_oracle_accuracy": image_report["overall_accuracy"],
                "video_oracle_accuracy": video_report["overall_accuracy"],
                "out": str(target),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
