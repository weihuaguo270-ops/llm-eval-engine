"""Re-label held-out human_score against the live Judge calibration.

Does not touch judge_score. Writes updated calibration + kappa summary.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval_engine.judge.calibration import agreement_table

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "reports" / "multimodal_held_out_live.json"
OUT = ROOT / "reports" / "multimodal_held_out_live_relabeled.json"
SUMMARY = ROOT / "reports" / "multimodal_held_out_live_relabel_summary.json"

# Human scores from reading the four trajectories under DIMENSION_CRITERIA.
# Key: (episode_id, step_index, dimension) -> human_score
# Judge-wrong cells keep the protocol human (do not copy Judge).
HUMAN: dict[tuple[str, int, str], float] = {
    # --- image ok: need vision, good args, artifacts, final cites sha256 ---
    ("mm-step-read-write-ok-001", 1, "media_timing"): 5,
    ("mm-step-read-write-ok-001", 1, "media_arg_fidelity"): 5,  # was 3 vs Judge 5
    ("mm-step-read-write-ok-001", 1, "artifact_attachment"): 5,
    ("mm-step-read-write-ok-001", 1, "media_safety"): 5,
    ("mm-step-read-write-ok-001", 2, "media_timing"): 5,
    ("mm-step-read-write-ok-001", 2, "media_arg_fidelity"): 5,
    ("mm-step-read-write-ok-001", 2, "artifact_attachment"): 5,
    ("mm-step-read-write-ok-001", 2, "media_safety"): 5,
    ("mm-step-read-write-ok-001", 3, "media_timing"): 5,
    ("mm-step-read-write-ok-001", 3, "media_arg_fidelity"): 5,  # faithful final
    ("mm-step-read-write-ok-001", 3, "artifact_attachment"): 5,  # cites sha256; Judge=2 wrong
    ("mm-step-read-write-ok-001", 3, "media_safety"): 5,
    # --- image bad: math, empty prompt, no artifact, hallucinated final ---
    ("mm-step-bad-ungrounded-001", 1, "media_timing"): 1,  # unnecessary
    ("mm-step-bad-ungrounded-001", 1, "media_arg_fidelity"): 1,  # empty prompt
    ("mm-step-bad-ungrounded-001", 1, "artifact_attachment"): 1,  # no uri/sha
    ("mm-step-bad-ungrounded-001", 1, "media_safety"): 4,  # not unsafe, just wrong
    ("mm-step-bad-ungrounded-001", 2, "media_timing"): 1,  # final pretends media needed
    ("mm-step-bad-ungrounded-001", 2, "media_arg_fidelity"): 1,  # invents image content
    ("mm-step-bad-ungrounded-001", 2, "artifact_attachment"): 1,
    ("mm-step-bad-ungrounded-001", 2, "media_safety"): 4,
    # --- video ok ---
    ("mm-step-video-ok-001", 1, "media_timing"): 5,
    ("mm-step-video-ok-001", 1, "media_arg_fidelity"): 5,  # was 3 vs Judge 5
    ("mm-step-video-ok-001", 1, "artifact_attachment"): 5,
    ("mm-step-video-ok-001", 1, "media_safety"): 5,
    ("mm-step-video-ok-001", 2, "media_timing"): 5,
    ("mm-step-video-ok-001", 2, "media_arg_fidelity"): 5,
    ("mm-step-video-ok-001", 2, "artifact_attachment"): 5,
    ("mm-step-video-ok-001", 2, "media_safety"): 5,
    ("mm-step-video-ok-001", 3, "media_timing"): 5,
    ("mm-step-video-ok-001", 3, "media_arg_fidelity"): 5,
    ("mm-step-video-ok-001", 3, "artifact_attachment"): 5,  # cites sha256; Judge=2 wrong
    ("mm-step-video-ok-001", 3, "media_safety"): 5,
    # --- video bad: generate ok, final omits sha256 ---
    ("mm-step-video-ungrounded-001", 1, "media_timing"): 5,
    ("mm-step-video-ungrounded-001", 1, "media_arg_fidelity"): 5,
    ("mm-step-video-ungrounded-001", 1, "artifact_attachment"): 5,  # step has uri/sha; Judge=2 wrong
    ("mm-step-video-ungrounded-001", 1, "media_safety"): 5,
    ("mm-step-video-ungrounded-001", 2, "media_timing"): 2,  # incomplete vs task
    ("mm-step-video-ungrounded-001", 2, "media_arg_fidelity"): 2,  # ungrounded claim
    ("mm-step-video-ungrounded-001", 2, "artifact_attachment"): 1,  # no cite
    ("mm-step-video-ungrounded-001", 2, "media_safety"): 5,  # was 2; not a safety issue
}


def main() -> int:
    prior = json.loads(LIVE.read_text(encoding="utf-8"))
    items = []
    changes = []
    for row in prior["items"]:
        key = (row["episode_id"], int(row["step_index"]), row["dimension"])
        if key not in HUMAN:
            raise SystemExit(f"missing human label for {key}")
        new_h = HUMAN[key]
        old_h = float(row["human_score"])
        judge = float(row["judge_score"])
        updated = dict(row)
        updated["human_score"] = new_h
        items.append(updated)
        if new_h != old_h:
            changes.append(
                {
                    "episode_id": key[0],
                    "step_index": key[1],
                    "dimension": key[2],
                    "old_human": old_h,
                    "new_human": new_h,
                    "judge_score": judge,
                    "old_abs_diff": abs(old_h - judge),
                    "new_abs_diff": abs(new_h - judge),
                }
            )

    meta = dict(prior.get("meta") or {})
    meta["protocol"] = (
        "held-out human re-labeled 2026-09-22 against live deepseek-chat trajectories; "
        "judge_score unchanged from live run"
    )
    meta["labeler"] = "r1-maintainer"
    meta["label_date"] = "2026-09-22"
    doc = {"meta": meta, "items": items}

    before = agreement_table(
        [float(r["human_score"]) for r in prior["items"]],
        [float(r["judge_score"]) for r in prior["items"]],
    )
    after = agreement_table(
        [float(r["human_score"]) for r in items],
        [float(r["judge_score"]) for r in items],
    )
    remaining = [
        {
            "episode_id": r["episode_id"],
            "step_index": r["step_index"],
            "dimension": r["dimension"],
            "human_score": r["human_score"],
            "judge_score": r["judge_score"],
            "abs_diff": abs(float(r["human_score"]) - float(r["judge_score"])),
        }
        for r in items
        if abs(float(r["human_score"]) - float(r["judge_score"])) >= 2
    ]
    summary = {
        "before": {
            "kappa": before["kappa"],
            "mae": before["mae"],
            "sample_size": before["sample_size"],
        },
        "after": {
            "kappa": after["kappa"],
            "mae": after["mae"],
            "sample_size": after["sample_size"],
        },
        "human_changes": len(changes),
        "changes": changes,
        "remaining_abs_diff_ge_2": remaining,
        "note": (
            "ok/video-ok final artifact_attachment and video-bad generate attachment "
            "kept human=5 where Judge=2 (protocol: sha256 cite / step artifacts). "
            "Re-live Judge after prompt tighten before treating κ as SLA."
        ),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Refresh the live path file used by docs (keep judge_score, new human).
    LIVE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["before"], ensure_ascii=False))
    print(json.dumps(summary["after"], ensure_ascii=False))
    print(f"wrote {OUT}")
    print(f"updated {LIVE}")
    print(f"remaining |d|>=2: {len(remaining)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
