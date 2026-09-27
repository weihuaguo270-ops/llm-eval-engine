"""Sync fixture-calibration human_score to the 2026-09-22 live re-label.

Keeps fixture judge_score unchanged so offline CI still binds to frozen
episode judge_scores. Live κ uses reports/multimodal_held_out_live.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "fixtures" / "calibration" / "multimodal_dimension_held_out.json"
LIVE = ROOT / "reports" / "multimodal_held_out_live.json"


def main() -> int:
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    human = {
        (row["episode_id"], int(row["step_index"]), row["dimension"]): float(
            row["human_score"]
        )
        for row in live["items"]
    }
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed = 0
    for row in fixture["items"]:
        key = (row["episode_id"], int(row["step_index"]), row["dimension"])
        if key in human and float(row["human_score"]) != human[key]:
            row["human_score"] = human[key]
            changed += 1
    meta = dict(fixture.get("meta") or {})
    meta["human_label_date"] = "2026-09-22"
    meta["human_label_note"] = (
        "human_score synced from live trajectory re-label; "
        "judge_score remains fixture-frozen for offline binding"
    )
    fixture["meta"] = meta
    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"updated human_score cells: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
