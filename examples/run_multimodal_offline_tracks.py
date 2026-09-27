"""Run multimodal understanding offline_real track.

Generation-side model selection has been removed from this repository.

Examples:
  PYTHONPATH=src python examples/run_multimodal_offline_tracks.py --out reports/mm-tracks
  PYTHONPATH=src python examples/run_multimodal_offline_tracks.py --smoke
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.multimodal import run_multimodal_offline_tracks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/multimodal-offline-tracks"),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Tiny held-out-preserving slice for CI wiring checks.",
    )
    args = parser.parse_args()
    report = run_multimodal_offline_tracks(
        args.out, tracks=("understanding",), smoke=args.smoke
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "summary": report["summary"],
                "all_tracks_offline_real": report["all_tracks_offline_real"],
                "claim_boundary": report["claim_boundary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["all_tracks_offline_real"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
