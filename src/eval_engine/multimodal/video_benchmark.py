"""Dataset, artifact and gate contracts for real text-to-video evaluation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


def build_video_prompt_dataset() -> list[dict[str, Any]]:
    """Build the frozen 30-case prompt set with dev/golden/held-out splits."""
    prompts = (
        ("motion", "A red toy car drives from left to right across a white table."),
        ("motion", "A blue ball rolls down a wooden ramp and stops."),
        ("motion", "A paper airplane glides through a quiet classroom."),
        ("motion", "A cyclist passes behind a park bench on a sunny day."),
        ("motion", "Three balloons rise slowly into a clear sky."),
        ("camera", "Camera pushes slowly toward a steaming cup of coffee."),
        ("camera", "Camera pans right across a row of colorful books."),
        ("camera", "A smooth orbit shot around a green hiking backpack."),
        ("camera", "Camera tilts upward from a street to a glass tower."),
        ("camera", "A slow zoom out reveals a small fishing harbor."),
        ("temporal", "A white flower opens gradually in morning light."),
        ("temporal", "Ice cubes melt slowly in a transparent glass."),
        ("temporal", "A candle flame flickers while the candle stays still."),
        ("temporal", "Cloud shadows move across a green mountain valley."),
        ("temporal", "Raindrops collect and slide down a window."),
        ("interaction", "A hand places a red apple beside a yellow banana."),
        ("interaction", "A robot arm moves one parcel onto a conveyor belt."),
        ("interaction", "Two people exchange a blue folder in an office."),
        ("interaction", "A spoon stirs sugar into a cup of tea."),
        ("interaction", "A dog catches a soft ball and returns it."),
        ("scene", "Pedestrians cross a rainy city street at night."),
        ("scene", "Small waves reach a sandy beach before sunrise."),
        ("scene", "Leaves move gently on trees beside a quiet library."),
        ("scene", "A train crosses a stone bridge in the mountains."),
        ("scene", "Lanterns sway above an empty evening market."),
        ("counting", "Exactly two glass bottles rotate slowly on a table."),
        ("counting", "Five yellow pencils move into a neat row."),
        ("spatial", "A blue cube moves behind a stationary red sphere."),
        ("spatial", "A small boat travels under a stone bridge."),
        ("spatial", "A bicycle moves from foreground to background along a path."),
    )
    cases = []
    for index, (category, prompt) in enumerate(prompts):
        split = "dev" if index < 6 else "golden" if index < 21 else "held_out"
        cases.append({"id": f"video-{index + 1:02d}", "split": split,
                      "source_cluster": f"{category}-{index + 1:02d}",
                      "task_type": "text_to_video", "category": category,
                      "prompt": prompt, "safety_expected": "benign", "license": "CC0-1.0"})
    return cases


def video_dataset_manifest(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate dataset cardinality and return its reproducibility fingerprint."""
    if len(cases) != 30 or len({case["id"] for case in cases}) != 30:
        raise ValueError("video benchmark requires exactly 30 unique prompts")
    canonical = json.dumps(list(cases), sort_keys=True, separators=(",", ":"))
    return {"schema_version": "video-prompt-dataset/v1", "case_count": 30,
            "split_counts": dict(sorted(Counter(case["split"] for case in cases).items())),
            "fingerprint_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "source": "project-authored prompts", "license": "CC0-1.0"}


def video_artifact_record(path: str | Path, *, case: Mapping[str, Any], model: Mapping[str, Any],
                          seed: int, latency_ms: float, config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a generated video and bind its media metadata to one model run.

    This validates artifact existence and basic decodability, not semantic quality.
    Semantic and safety metrics are attached by downstream evaluators.
    """
    target = Path(path)
    if not target.is_file() or target.stat().st_size == 0:
        raise ValueError(f"missing video artifact: {target}")
    import imageio.v3 as iio

    frames = iio.imread(target, index=None)
    if frames.ndim != 4 or frames.shape[0] < 2 or not float(frames.var()) > 0:
        raise ValueError("video must contain multiple nonblank RGB frames")
    fps = float(config["fps"])
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {"case_id": case["id"], "split": case["split"], "task_type": "text_to_video",
            "prompt": case["prompt"], "model": model["id"], "model_version": model["revision"],
            "model_license": model["license"], "seed": seed, "generation_config": dict(config),
            "artifacts": [{"id": f"{case['id']}::{model['alias']}", "media_type": "video",
                           "uri": target.resolve().as_posix(), "mime_type": "video/mp4", "sha256": digest,
                           "width": int(frames.shape[2]), "height": int(frames.shape[1]),
                           "frame_count": int(frames.shape[0]),
                           "duration_ms": round(frames.shape[0] / fps * 1000), "bytes": target.stat().st_size}],
            "latency_ms": round(latency_ms, 3), "cost": 0.0,
            "cost_basis": "local GPU with CPU offload; hardware/electricity excluded"}


def video_completion_gate(records: Sequence[Mapping[str, Any]], *, expected_cases: int = 30) -> dict[str, Any]:
    """Require complete two-model evidence before claiming a real offline run.

    The gate checks coverage, readable multi-frame artifacts, automatic metrics,
    safety results and held-out inclusion. It does not claim human preference or
    online production evidence.
    """
    cases = {str(row.get("case_id", "")) for row in records}
    models = {str(row.get("model", "")) for row in records}
    artifacts = [item for row in records for item in row.get("artifacts", [])]
    checks = {"case_count": len(cases) == expected_cases, "model_count": len(models) == 2,
              "record_count": len(records) == expected_cases * 2,
              "real_videos": bool(artifacts) and all(Path(item["uri"]).is_file()
                                                      and item.get("frame_count", 0) >= 2
                                                      and item.get("duration_ms", 0) > 0 for item in artifacts),
              "automatic_metrics": bool(records) and all(row.get("automatic_metrics") for row in records),
              "safety_results": bool(records) and all(row.get("safety_result") is not None for row in records),
              "held_out": any(row.get("split") == "held_out" for row in records)}
    return {"passed": all(checks.values()), "checks": checks,
            "evidence_level": "offline_real" if all(checks.values()) else "interface"}
