"""Run a resumable two-model image-generation evaluation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.multimodal import (  # noqa: E402
    ClipSafetyScorer,
    DEFAULT_MODELS,
    LocalDiffusersGenerator,
    analyze_blind_ratings,
    analyze_panel_ratings,
    build_blind_review,
    build_panel_batches,
    build_prompt_dataset,
    completion_gate,
    compare_model_records,
    dataset_manifest,
    panel_review_progress,
)


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def initialize(output: Path) -> dict:
    cases = build_prompt_dataset()
    payload = {"dataset": dataset_manifest(cases), "cases": cases, "models": list(DEFAULT_MODELS),
               "evidence_boundary": "Configuration only until the completion gate passes."}
    write_json(output / "dataset.json", payload)
    return payload


def generate(output: Path, smoke: bool = False) -> dict:
    source = read_json(output / "dataset.json", None) or initialize(output)
    cases = source["cases"][:1] if smoke else source["cases"]
    target = output / ("smoke_records.json" if smoke else "generation_records.json")
    records = read_json(target, [])
    completed = {(row["case_id"], row["model"]) for row in records}
    for model in source["models"]:
        runner = LocalDiffusersGenerator(model)
        try:
            for index, case in enumerate(cases):
                if (case["id"], model["id"]) in completed:
                    continue
                path = output / "artifacts" / model["alias"] / f"{case['id']}.png"
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
    scorer = ClipSafetyScorer()
    for record in records:
        if not record.get("automatic_metrics") or not record.get("safety_result"):
            record["automatic_metrics"], record["safety_result"] = scorer.score(record)
            write_json(target, records)
    return {"records": len(records), "scored": sum(bool(row.get("automatic_metrics")) for row in records),
            "safe": sum(bool((row.get("safety_result") or {}).get("passed")) for row in records)}


def prepare_review(output: Path, smoke: bool = False) -> dict:
    records = read_json(output / ("smoke_records.json" if smoke else "generation_records.json"), [])
    blind = build_blind_review(records)
    worksheet = blind.pop("worksheet")
    blind["private_key"] = blind.pop("private_key")
    prefix = "smoke_" if smoke else ""
    write_json(output / f"{prefix}blind_review_key.json", blind)
    names = (f"{prefix}rater_1.json", f"{prefix}rater_2.json")
    for name in names:
        target = output / name
        existing = read_json(target, [])
        started = any(str(row.get("rater_id", "")).strip() for row in existing)
        if not target.exists() or (not started and len(existing) != len(worksheet)):
            write_json(target, worksheet)
    return {"entries": len(worksheet), "worksheets": list(names)}


def prepare_panel(output: Path) -> dict:
    manifest_path = output / "panel_review_manifest.json"
    if manifest_path.is_file():
        manifest = read_json(manifest_path, {})
        return {"manifest": str(manifest_path), "batches": manifest.get("batches", []), "preserved": True}
    source = read_json(output / "rater_1.json", [])
    result = build_panel_batches(source)
    write_json(manifest_path, result["manifest"])
    for filename, rows in result["worksheets"].items():
        target = output / filename
        if target.exists():
            raise ValueError(f"panel worksheet already exists without a manifest: {target}")
        write_json(target, rows)
    return {"manifest": str(manifest_path), "batches": result["manifest"]["batches"],
            "preserved": False}


def finalize(output: Path, smoke: bool = False) -> dict:
    records = read_json(output / ("smoke_records.json" if smoke else "generation_records.json"), [])
    prefix = "smoke_" if smoke else ""
    key = read_json(output / f"{prefix}blind_review_key.json", {}).get("private_key") or {}
    panel_manifest = read_json(output / "panel_review_manifest.json", None) if not smoke else None
    if panel_manifest:
        batches = {str(batch["worksheet"]): read_json(output / str(batch["worksheet"]), [])
                   for batch in panel_manifest.get("batches", [])}
        primary = read_json(output / "rater_1.json", [])
        full = read_json(output / "rater_2.json", [])
        try:
            review = analyze_panel_ratings(panel_manifest, primary, full, batches, key)
        except ValueError as exc:
            review = panel_review_progress(panel_manifest, primary, full, batches)
            review["pending_reason"] = str(exc)
    else:
        try:
            review = analyze_blind_ratings([read_json(output / f"{prefix}rater_1.json", []),
                                            read_json(output / f"{prefix}rater_2.json", [])], key)
        except ValueError as exc:
            review = {"rater_count": 0, "shared_entries": 0, "pending_reason": str(exc)}
    gate = completion_gate(records, review, expected_cases=1 if smoke else 100)
    by_model = {}
    for model in sorted({row["model"] for row in records}):
        rows = [row for row in records if row["model"] == model]
        scored = [row for row in rows if row.get("automatic_metrics")]
        by_model[model] = {"samples": len(rows),
                           "mean_latency_ms": round(sum(row["latency_ms"] for row in rows) / len(rows), 3),
                           "mean_clip_cosine": round(sum(row["automatic_metrics"]["clip_cosine"]
                                                         for row in scored) / len(scored), 6) if scored else None}
    comparison = compare_model_records(records) if records and all(row.get("automatic_metrics") for row in records) else None
    report = {"schema_version": "real-image-benchmark-report/v1", "record_count": len(records),
              "model_summary": by_model, "automatic_comparison": comparison,
              "blind_review": review, "completion_gate": gate,
              "supply_chain_notes": [
                  "Both configured image pipelines require safetensors weights; model commits and licenses are recorded."
              ]}
    write_json(output / ("smoke_report.json" if smoke else "final_report.json"), report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "generate", "score", "prepare-review",
                                             "prepare-panel", "finalize"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    actions = {"init": lambda: initialize(args.output), "generate": lambda: generate(args.output, args.smoke),
               "score": lambda: score(args.output, args.smoke),
               "prepare-review": lambda: prepare_review(args.output, args.smoke),
               "prepare-panel": lambda: prepare_panel(args.output),
               "finalize": lambda: finalize(args.output, args.smoke)}
    result = actions[args.command]()
    if args.command == "init":
        result = {"dataset": result["dataset"], "models": result["models"],
                  "output": str(args.output / "dataset.json")}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == "finalize" and not result["completion_gate"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
