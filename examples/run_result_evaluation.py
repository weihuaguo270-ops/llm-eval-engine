"""结果判断（**常规产出**）：把校准分数变成判定，并给出**决策级**指标。

与 `run_calibration.py` 的分工（**并列，不合成**）：

============================  ==========================================
`run_calibration.py`          人机校准：κ / MAE / CI —— **分数级**一致性
本脚本                        结果判断：**决策级**一致率 + 缺陷率 + 误杀/漏杀 + CI
============================  ==========================================

为什么需要它：κ 把「1↔2」与「2↔3」同等看待，但前者**不改变任何结论**、后者会翻转结论。
只报 κ 回答不了「这套 Rubric 能不能拿去做门禁」。

合格线来源：`src/eval_engine/dataset/data/verdict_bands_line1.json`
（逐字引用 `calibration_human_judge.json` 的 `meta.labeling_protocol` 刻度锚点**并留出处**）。

用法::

    python examples/run_result_evaluation.py                      # 用最近一份 live 报告
    python examples/run_result_evaluation.py --report <path> --split held_out|dev|all
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

# Windows 控制台常见 GBK：报告里含 ⚠️ 等字符时会崩 → 强制 UTF-8（坏字符替换）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

from eval_engine.core.verdict import (  # noqa: E402
    bands_identity,
    clustered_rate_ci,
    load_bands,
    load_bands_document,
    verdict_for,
)

DATA_DIR = REPO / "src" / "eval_engine" / "dataset" / "data"
DEFAULT_BANDS = DATA_DIR / "verdict_bands_line1.json"
GOLDEN = DATA_DIR / "calibration_human_judge.json"
REPORTS = REPO / "reports"
#: 簇少于这个数时**不报**聚簇 CI（重采样对象太少 → 区间退化，会给出误导性的窄区间）
MIN_CLUSTERS_FOR_CLUSTER_CI = 10


# 合格线加载器**统一在 core**（`load_bands` / `load_bands_document`）。
# 本文件曾自带一份只认外壳键 `bands` 的副本，而 core 那份只认 `verdict_bands`——
# 同一份内容两种读法会给出**不同判定**（同一维度 5 分：一种 `pass`、一种 `unbanded`），
# 且**都不报错**。故不再各留一份。


def template_of_item(golden: dict[str, Any]) -> dict[str, str]:
    return {str(i["id"]): str(i.get("template") or "unknown") for i in golden["items"]}


def latest_live_report() -> Path:
    reports = sorted(REPORTS.glob("calibration_report_*_live.json"))
    if not reports:
        raise SystemExit("找不到 calibration_report_*_live.json（先跑 run_calibration.py --live）")
    return reports[-1]


def evaluate(
    rows: list[dict[str, Any]], bands: dict[str, Any], label: str
) -> dict[str, Any]:
    """一行一条样本：算判定分布、缺陷率、**决策级一致率**、误杀/漏杀、率 CI。"""
    human_counts: Counter = Counter()
    judge_counts: Counter = Counter()
    pairs: Counter = Counter()
    per_item_defect: dict[str, int] = {}
    per_template_defect: dict[str, int] = defaultdict(int)
    per_template_total: dict[str, int] = defaultdict(int)
    for row in rows:
        tpl, human, judge = row["template"], row["human"], row["judge"]
        verdict_h = verdict_for(tpl, human, bands)
        verdict_j = verdict_for(tpl, judge, bands)
        human_counts[verdict_h] += 1
        judge_counts[verdict_j] += 1
        pairs[(verdict_h, verdict_j)] += 1
        per_item_defect[f"i{len(per_item_defect)}"] = 1 if verdict_j == "defect" else 0
        per_template_total[tpl] += 1
        if verdict_j == "defect":
            per_template_defect[tpl] += 1
    n = sum(judge_counts.values()) or 1
    agree = sum(v for (a, b), v in pairs.items() if a == b)
    kill = pairs.get(("pass", "defect"), 0) + pairs.get(("marginal", "defect"), 0)
    miss = pairs.get(("defect", "pass"), 0) + pairs.get(("defect", "marginal"), 0)
    low, high = clustered_rate_ci(per_item_defect, {k: 1 for k in per_item_defect})
    cluster_note = None
    if len(per_template_total) >= MIN_CLUSTERS_FOR_CLUSTER_CI:
        c_low, c_high = clustered_rate_ci(per_template_defect, per_template_total)
        cluster_ci = [round(c_low, 3), round(c_high, 3)]
    else:
        cluster_ci = None
        cluster_note = f"簇数 {len(per_template_total)} < {MIN_CLUSTERS_FOR_CLUSTER_CI} → **不报聚簇 CI**（会退化）"
    return {
        "label": label,
        "n": n,
        "human_verdicts": dict(human_counts),
        "judge_verdicts": dict(judge_counts),
        "human_defect_rate": round(human_counts.get("defect", 0) / n, 4),
        "judge_defect_rate": round(judge_counts.get("defect", 0) / n, 4),
        "defect_rate_ci_item": [round(low, 3), round(high, 3)],
        "defect_rate_ci_cluster": cluster_ci,
        "cluster_note": cluster_note,
        "decision_agreement": round(agree / n, 4),
        "false_kill": kill,
        "false_pass": miss,
        "verdict_pairs": {f"{a}->{b}": v for (a, b), v in sorted(pairs.items())},
    }


def render(
    blocks: list[dict[str, Any]],
    document: dict[str, Any],
    identity: dict[str, Any],
    source: Path,
    mode: str,
) -> str:
    # 身份**随数字走**：数字离开这份报告时，读者仍能知道它依赖哪一份合格线
    identified = (
        f"`{identity['sha256'][:16]}`（{len(identity['dimensions'])} 维）"
        if identity["recognized"]
        else f"**不可识别**（{identity['reason']} → 判定会全落成 `unbanded`）"
    )
    lines = [
        "# 结果判断（决策级）",
        "",
        f"- **栏位：`{mode}`**",
        "",
        f"- 数据来源：`{source.relative_to(REPO).as_posix()}`",
        f"- 合格线出处：{document['provenance']['field']} — 「{document['provenance']['verbatim']}」",
        f"- 推导：{document['derivation']}",
        f"- 合格线身份：{identity['algo']}｜{identified}",
        "",
        "> 与 `run_calibration.py` 的 **κ（分数级）并列，不合成**。",
        "",
    ]
    if mode != "live":
        lines += [
            f"> ⚠️ **本报告来自 `{mode}` 栏，不是 live 栏** → 只能证明「复现/冻结」一致，"
            "**不得作为 Judge 可信度或结果判断的依据**（引用前先看栏位）。",
            "",
        ]
    for b in blocks:
        lines += [
            f"## {b['label']}（n={b['n']}）",
            "",
            "| 判定 | 人工 | Judge |",
            "|---|---:|---:|",
            f"| pass | {b['human_verdicts'].get('pass', 0)} | {b['judge_verdicts'].get('pass', 0)} |",
            f"| marginal | {b['human_verdicts'].get('marginal', 0)} | {b['judge_verdicts'].get('marginal', 0)} |",
            f"| defect | {b['human_verdicts'].get('defect', 0)} | {b['judge_verdicts'].get('defect', 0)} |",
            f"| undecidable | {b['human_verdicts'].get('undecidable', 0)} | {b['judge_verdicts'].get('undecidable', 0)} |",
            "",
            f"- **缺陷率**：人工 {b['human_defect_rate']:.1%}｜Judge {b['judge_defect_rate']:.1%}"
            f"（95% CI item 级 {b['defect_rate_ci_item']}）",
            f"- **决策级一致率**：{b['decision_agreement']:.1%}"
            f"（误杀 {b['false_kill']} 格：人判非缺陷而 Judge 判缺陷；"
            f"漏杀 {b['false_pass']} 格：人判缺陷而 Judge 放过）",
            f"- 判定交叉表：{b['verdict_pairs']}",
        ]
        if b["cluster_note"]:
            lines.append(f"- 聚簇 CI：{b['cluster_note']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="结果判断（决策级常规产出）")
    parser.add_argument("--report", type=Path, default=None, help="校准报告 JSON（默认取最近一份 live）")
    parser.add_argument("--bands", type=Path, default=DEFAULT_BANDS)
    parser.add_argument("--split", default="held_out", choices=("held_out", "dev", "all"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    # 维度层交给判定；整份文档留给口径出处（`provenance` / `derivation`）
    bands = load_bands(args.bands)
    document = load_bands_document(args.bands)
    # 【P1】合格线**内容身份**：只算、只记录——本脚本不改判定行为。
    identity = bands_identity(args.bands)
    templates = template_of_item(json.loads(GOLDEN.read_text(encoding="utf-8")))
    # 统一解析为**绝对路径**：否则 `--report` 传相对路径时 `relative_to(REPO)` 会抛异常
    report_path = Path(args.report or latest_live_report()).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    pairs = report.get("pairs") or []
    rows = [
        {"id": p["id"], "template": templates.get(str(p["id"]), "unknown"),
         "human": p.get("human"), "judge": p.get("judge"), "split": p.get("split")}
        for p in pairs
    ]
    if args.split != "all":
        rows = [r for r in rows if str(r.get("split") or "held_out") == args.split]

    mode = str(report.get("mode") or "unknown")
    tag = f"{args.split}｜{mode} 栏" + ("（真实 Rubric）" if mode == "live" else "（非 live：只作复现证据）")
    blocks = [evaluate(rows, bands, tag)]
    for tpl in sorted({r["template"] for r in rows}):
        blocks.append(evaluate([r for r in rows if r["template"] == tpl], bands, f"{args.split}｜template={tpl}"))

    text = render(blocks, document, identity, report_path, mode)
    out = args.out or (REPORTS / f"result_evaluation_{report_path.stem.split('_')[-2]}_{args.split}.md")
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"[written] {out.relative_to(REPO).as_posix()}")
    (out.with_suffix(".json")).write_text(
        json.dumps(
            {
                "source": str(report_path),
                "split": args.split,
                "bands_identity": identity,
                "blocks": blocks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
