"""Run a resumable two-model text-to-video benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.multimodal.video_benchmark import (  # noqa: E402
    build_video_prompt_dataset,
    video_completion_gate,
    video_dataset_manifest,
)
from eval_engine.multimodal.video_generation import (  # noqa: E402
    LocalVideoGenerator, VIDEO_MODELS, VideoClipSafetyScorer,
)


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def initialize(output: Path) -> dict:
    cases = build_video_prompt_dataset()
    payload = {"dataset": video_dataset_manifest(cases), "cases": cases, "models": list(VIDEO_MODELS),
               "license_boundary": "ModelScope is CC-BY-NC-4.0 and is a research-only comparison."}
    write_json(output / "dataset.json", payload)
    return payload


def generate(output: Path, smoke: bool = False) -> dict:
    source = read_json(output / "dataset.json", None) or initialize(output)
    cases = source["cases"][:1] if smoke else source["cases"]
    target = output / ("smoke_records.json" if smoke else "generation_records.json")
    records = read_json(target, [])
    completed = {(row["case_id"], row["model"]) for row in records}
    for model in source["models"]:
        runner = LocalVideoGenerator(model)
        try:
            for index, case in enumerate(cases):
                if (case["id"], model["id"]) in completed:
                    continue
                path = output / "artifacts" / model["alias"] / f"{case['id']}.mp4"
                records.append(runner.generate(case, path, 20260813 + index))
                write_json(target, records)
        finally:
            runner.close()
    return {"records": len(records), "models": sorted({row["model"] for row in records})}


def score(output: Path, smoke: bool = False) -> dict:
    target = output / ("smoke_records.json" if smoke else "generation_records.json")
    records = read_json(target, [])
    if not records:
        raise ValueError("generation records are required before scoring")
    scorer = VideoClipSafetyScorer()
    for record in records:
        if not record.get("automatic_metrics") or record.get("safety_result") is None:
            record["automatic_metrics"], record["safety_result"] = scorer.score(record)
            write_json(target, records)
    return {"records": len(records), "scored": sum(bool(row.get("automatic_metrics")) for row in records),
            "safe": sum(bool((row.get("safety_result") or {}).get("passed")) for row in records)}


def finalize(output: Path, smoke: bool = False) -> dict:
    records = read_json(output / ("smoke_records.json" if smoke else "generation_records.json"), [])
    gate = video_completion_gate(records, expected_cases=1 if smoke else 30)
    report = {"schema_version": "real-video-benchmark-report/v1", "records": len(records),
              "completion_gate": gate,
              "license_boundary": "ModelScope output is restricted to non-commercial research comparison."}
    write_json(output / ("smoke_report.json" if smoke else "final_report.json"), report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "generate", "score", "finalize"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    result = {"init": lambda: initialize(args.output),
              "generate": lambda: generate(args.output, args.smoke),
              "score": lambda: score(args.output, args.smoke),
              "finalize": lambda: finalize(args.output, args.smoke)}[args.command]()
    if args.command == "init":
        result = {"dataset": result["dataset"], "models": result["models"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == "finalize" and not result["completion_gate"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
