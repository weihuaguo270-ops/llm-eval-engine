"""Regenerate docs/second_rater_worksheet.md from held_out prompts (blind)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "src/eval_engine/dataset/data/calibration_human_judge.json"
OUT = ROOT / "docs/second_rater_worksheet.md"


def main() -> None:
    data = json.loads(CAL.read_text(encoding="utf-8"))
    held = sorted(
        [x for x in data["items"] if x.get("split") == "held_out"],
        key=lambda x: int(x["id"].split("_")[1]),
    )
    lines = [
        "# 第二标注者工作表（盲评）",
        "",
        "> 只填 `r2_score`；不要打开含 human_score / judge_score 的完整 JSON 对照。",
        "> 协议：`docs/SECOND_RATER_PROTOCOL.md` + 数据文件 `meta.labeling_protocol`（含边界 v2 / 灰区 v2.1）。",
        "> 打完后把分数回填到 `calibration_human_judge.json` 的 `human_score_r2`（可写 `annotator_r2`）。",
        "",
        "| id | template | split | prompt | r2_score | reason |",
        "|----|----------|-------|--------|---------:|--------|",
    ]
    for x in held:
        prompt = (x.get("prompt") or "").replace("|", "\\|")
        lines.append(
            f"| {x['id']} | {x.get('template', '')} | held_out | {prompt} |  |  |"
        )
    lines.append("")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} rows={len(held)}")


if __name__ == "__main__":
    main()
