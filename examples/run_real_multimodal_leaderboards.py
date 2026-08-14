"""Build versioned image and video leaderboards from real benchmark records."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.benchmark.leaderboard import analyze_paired_leaderboard  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(image_records: Path, video_records: Path) -> dict:
    image = analyze_paired_leaderboard(read_json(image_records), metric="automatic_metrics.clip_cosine")
    video_clip = analyze_paired_leaderboard(read_json(video_records), metric="automatic_metrics.clip_frame_cosine_mean")
    video_temporal = analyze_paired_leaderboard(read_json(video_records), metric="automatic_metrics.temporal_consistency")
    checks = {"real_image_records": image["paired_cases"] == 100,
              "real_video_records": video_clip["paired_cases"] == 30,
              "uncertainty": all("difference_bootstrap_95_ci" in report
                                 for report in (image, video_clip, video_temporal)),
              "held_out": all(all(row["held_out_mean_score"] is not None for row in report["ranking"])
                              for report in (image, video_clip, video_temporal))}
    return {"schema_version": "real-multimodal-leaderboards/v1", "run_date": "2026-08-13",
            "sources": [{"path": image_records.as_posix(), "sha256": fingerprint(image_records)},
                        {"path": video_records.as_posix(), "sha256": fingerprint(video_records)}],
            "leaderboards": {"image_clip": image, "video_clip": video_clip,
                             "video_temporal_consistency": video_temporal},
            "completion_gate": {"passed": all(checks.values()), "checks": checks,
                                "evidence_level": "offline_real" if all(checks.values()) else "interface"},
            "interpretation": "A model may lead one metric and lose on latency, temporal consistency, safety, license, or human preference; there is no universal winner."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-records", type=Path, required=True)
    parser.add_argument("--video-records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.image_records, args.video_records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, args.output)
    print(json.dumps({"leaders": {name: value["leader"] for name, value in report["leaderboards"].items()},
                      "completion_gate": report["completion_gate"]}, ensure_ascii=False, indent=2))
    return 0 if report["completion_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
