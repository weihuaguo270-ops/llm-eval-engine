"""Patch expand live human labels from seed; refresh audit calibration + MD."""

from __future__ import annotations

import json
from pathlib import Path

from eval_engine.gates.release_audit import _calibration_report
from eval_engine.judge.calibration import format_agreement_markdown

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    live_path = ROOT / "reports" / "multimodal_held_out_expand_live.json"
    human_path = (
        ROOT
        / "examples"
        / "fixtures"
        / "calibration"
        / "multimodal_held_out_expand_human.json"
    )
    audit_path = ROOT / "reports" / "release_audit_held_out_expand_live.json"
    md_path = ROOT / "docs" / "calibration_snapshot_20260922_live_held_out_multimodal_expand.md"

    live = json.loads(live_path.read_text(encoding="utf-8"))
    human = json.loads(human_path.read_text(encoding="utf-8"))
    hmap = {
        (r["episode_id"], int(r["step_index"]), r["dimension"]): float(r["human_score"])
        for r in human["items"]
    }
    for row in live["items"]:
        key = (row["episode_id"], int(row["step_index"]), row["dimension"])
        row["human_score"] = hmap[key]
    live_path.write_text(
        json.dumps(live, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    cal = _calibration_report(live["items"])
    assert cal is not None
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["calibration"] = cal
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    md = format_agreement_markdown(cal, title="多模态过程 held_out 校准快照（20260922 / live）")
    md += (
        "\n## κ 单位（钉死）\n\n"
        f"- 主单位: **`{cal['kappa_unit']}`**（episode × media/final step × dimension）\n"
        f"- episode_count: **{cal['episode_count']}**\n"
        f"- cell sample_size: **{cal['sample_size']}**\n"
        "- 轨迹过程分（min media step）只进发布门禁，**不**作为 κ 聚合单位\n"
        "- 与文本 Judge held_out（n=53 items）分栏；禁止合成总分\n"
    )
    md_path.write_text(md, encoding="utf-8")
    boot = cal["bootstrap"]["kappa"]
    print(
        f"kappa={cal['kappa']} n={cal['sample_size']} eps={cal['episode_count']} "
        f"ci=[{boot['low']}, {boot['high']}] needs={cal['needs_calibration']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
