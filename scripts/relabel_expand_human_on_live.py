"""Apply expand human re-labels onto live calibration; recompute kappa."""

from __future__ import annotations

import json
from pathlib import Path

from eval_engine.judge.calibration import agreement_table

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "reports" / "multimodal_held_out_expand_live.json"
HUMAN = (
    ROOT
    / "examples"
    / "fixtures"
    / "calibration"
    / "multimodal_held_out_expand_human.json"
)


def main() -> int:
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    human_doc = json.loads(HUMAN.read_text(encoding="utf-8"))
    human = {
        (r["episode_id"], int(r["step_index"]), r["dimension"]): float(r["human_score"])
        for r in human_doc["items"]
    }
    before = agreement_table(
        [float(r["human_score"]) for r in live["items"]],
        [float(r["judge_score"]) for r in live["items"]],
    )
    for row in live["items"]:
        key = (row["episode_id"], int(row["step_index"]), row["dimension"])
        if key in human:
            row["human_score"] = human[key]
    after = agreement_table(
        [float(r["human_score"]) for r in live["items"]],
        [float(r["judge_score"]) for r in live["items"]],
    )
    live["meta"] = dict(live.get("meta") or {})
    live["meta"]["human_relabel_note"] = (
        "2026-09-22: unsafe final safety→5; wrong-generate args→2 (protocol)"
    )
    LIVE.write_text(json.dumps(live, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("before", {k: before[k] for k in ("kappa", "mae", "sample_size")})
    print("after", {k: after[k] for k in ("kappa", "mae", "sample_size")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
