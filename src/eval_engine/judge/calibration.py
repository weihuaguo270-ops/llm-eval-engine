"""calibration — Judge 人机校准

定期把 Judge 分数与人类标注对齐，避免评分漂移。

推荐流程：
  1. 准备 10–20+ 条已人工打分的 Judge 输入（见 dataset/data/calibration_human_judge.json）
  2. 离线：用冻结的 judge_score 复现一致性表；在线：用 JudgeExecutor 重打分
  3. 看 κ、精确一致率、±1 一致率、MAE、偏差（bias）
  4. κ 或一致性过低时，收紧 rubric 措辞或加 few-shot，再复测

说明：
  - HITL（人工审批）≠ 人机校准；前者管执行权限，后者管评分对齐
  - 小样本 κ 方差大，报告里必须写清 sample_size
"""

from __future__ import annotations

import json
import os
import random
from typing import Any, Callable, Optional


# ──────────────────────────────────────────────
# 基础统计
# ──────────────────────────────────────────────


def _to_likert(scores: list[float], lo: int = 1, hi: int = 5) -> list[int]:
    """将分数四舍五入并裁剪到 Likert 整数刻度。"""
    out: list[int] = []
    for s in scores:
        try:
            v = int(round(float(s)))
        except (TypeError, ValueError):
            v = lo
        out.append(max(lo, min(hi, v)))
    return out


def cohens_kappa(
    human_scores: list[float],
    judge_scores: list[float],
    n_bins: int = 5,
    *,
    likert: bool = True,
    scale_min: int = 1,
    scale_max: int = 5,
) -> float:
    """计算 Cohen's κ

    默认按 Likert（1–5）整数类别计算，避免把两列分数各自归一化分箱导致的假 κ。

    κ 解读（经验，小样本需谨慎）：
      > 0.8  几乎完全一致
      0.6–0.8 高度一致
      0.4–0.6 中等
      < 0.4  较差，建议校准
    """
    if len(human_scores) != len(judge_scores) or not human_scores:
        return 0.0

    n = len(human_scores)

    if likert:
        h_lab = _to_likert(human_scores, scale_min, scale_max)
        j_lab = _to_likert(judge_scores, scale_min, scale_max)
        labels = list(range(scale_min, scale_max + 1))
        index = {lab: i for i, lab in enumerate(labels)}
        k = len(labels)
        matrix = [[0] * k for _ in range(k)]
        for h, j in zip(h_lab, j_lab):
            matrix[index[h]][index[j]] += 1
    else:
        # 兼容旧行为：按联合范围分箱
        def _discretize(scores: list[float], bins: int) -> list[int]:
            min_s, max_s = min(scores), max(scores)
            if max_s == min_s:
                return [0] * len(scores)
            return [
                min(bins - 1, int((s - min_s) / (max_s - min_s + 1e-6) * bins))
                for s in scores
            ]

        all_scores = list(human_scores) + list(judge_scores)
        h_lab = _discretize(human_scores, n_bins)
        # 用联合范围分箱，保证两侧同一套边界
        min_s, max_s = min(all_scores), max(all_scores)

        def _disc(s: float) -> int:
            if max_s == min_s:
                return 0
            return min(n_bins - 1, int((s - min_s) / (max_s - min_s + 1e-6) * n_bins))

        h_lab = [_disc(s) for s in human_scores]
        j_lab = [_disc(s) for s in judge_scores]
        k = n_bins
        matrix = [[0] * k for _ in range(k)]
        for h, j in zip(h_lab, j_lab):
            matrix[h][j] += 1

    po = sum(matrix[i][i] for i in range(k)) / n
    row_sums = [sum(row) for row in matrix]
    col_sums = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    pe = sum(row_sums[i] * col_sums[i] for i in range(k)) / (n * n)

    if pe >= 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 4)


def agreement_table(
    human_scores: list[float],
    judge_scores: list[float],
    *,
    scale_min: int = 1,
    scale_max: int = 5,
    ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """人机一致性汇总表（κ / 一致率 / MAE / bias / 混淆矩阵）。"""
    if len(human_scores) != len(judge_scores) or not human_scores:
        return {
            "sample_size": 0,
            "kappa": 0.0,
            "exact_agree_rate": 0.0,
            "within_one_rate": 0.0,
            "mae": 0.0,
            "bias": 0.0,
            "confusion": [],
            "pairs": [],
        }

    h = _to_likert(human_scores, scale_min, scale_max)
    j = _to_likert(judge_scores, scale_min, scale_max)
    n = len(h)
    exact = sum(1 for a, b in zip(h, j) if a == b)
    within_one = sum(1 for a, b in zip(h, j) if abs(a - b) <= 1)
    abs_err = [abs(a - b) for a, b in zip(h, j)]
    bias = sum(b - a for a, b in zip(h, j)) / n

    labels = list(range(scale_min, scale_max + 1))
    index = {lab: i for i, lab in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in range(len(labels))]
    for a, b in zip(h, j):
        matrix[index[a]][index[b]] += 1

    pair_ids = ids or [str(i) for i in range(n)]
    pairs = [
        {
            "id": pair_ids[i],
            "human": h[i],
            "judge": j[i],
            "abs_err": abs(h[i] - j[i]),
        }
        for i in range(n)
    ]

    return {
        "sample_size": n,
        "kappa": cohens_kappa(h, j, likert=True, scale_min=scale_min, scale_max=scale_max),
        "exact_agree_rate": round(exact / n, 4),
        "within_one_rate": round(within_one / n, 4),
        "mae": round(sum(abs_err) / n, 4),
        "bias": round(bias, 4),
        "scale": [scale_min, scale_max],
        "confusion_labels": labels,
        "confusion": matrix,
        "pairs": pairs,
    }


def bootstrap_ci(
    human_scores: list[float],
    judge_scores: list[float],
    *,
    n_boot: int = 2000,
    seed: int = 20260716,
    alpha: float = 0.05,
    scale_min: int = 1,
    scale_max: int = 5,
) -> dict[str, Any]:
    """对 κ / 精确一致率做百分位 bootstrap 置信区间（小样本趋势用）。"""
    n = len(human_scores)
    if n == 0 or n != len(judge_scores):
        return {"n_boot": 0, "seed": seed, "alpha": alpha}

    h0 = _to_likert(human_scores, scale_min, scale_max)
    j0 = _to_likert(judge_scores, scale_min, scale_max)
    rng = random.Random(seed)
    kappas: list[float] = []
    exacts: list[float] = []
    idx = list(range(n))
    for _ in range(n_boot):
        sample = [rng.choice(idx) for _ in range(n)]
        hs = [h0[i] for i in sample]
        js = [j0[i] for i in sample]
        kappas.append(cohens_kappa(hs, js, likert=True, scale_min=scale_min, scale_max=scale_max))
        exacts.append(sum(1 for a, b in zip(hs, js) if a == b) / n)

    def _pct(vals: list[float]) -> dict[str, float]:
        s = sorted(vals)
        lo_i = int((alpha / 2) * (len(s) - 1))
        hi_i = int((1 - alpha / 2) * (len(s) - 1))
        return {
            "point": round(sum(vals) / len(vals), 4),
            "low": round(s[lo_i], 4),
            "high": round(s[hi_i], 4),
        }

    return {
        "n_boot": n_boot,
        "seed": seed,
        "alpha": alpha,
        "kappa": _pct(kappas),
        "exact_agree_rate": _pct(exacts),
        "note": "百分位 bootstrap；小样本区间偏宽，仅作不确定性展示",
    }


def format_agreement_markdown(report: dict[str, Any], title: str = "人机校准报告") -> str:
    """把 agreement / calibrator 报告格式化为 Markdown。"""
    lines = [
        f"# {title}",
        "",
        f"- 样本量: **{report.get('sample_size', 0)}**",
        f"- Cohen's κ: **{report.get('kappa', 0)}**",
        f"- 精确一致率: **{report.get('exact_agree_rate', 0):.1%}**",
        f"- ±1 分一致率: **{report.get('within_one_rate', 0):.1%}**",
        f"- MAE: **{report.get('mae', 0)}**",
        f"- Bias (Judge − Human): **{report.get('bias', 0)}**",
    ]
    boot = report.get("bootstrap") or {}
    if boot.get("kappa"):
        k = boot["kappa"]
        lines.append(
            f"- κ bootstrap {int((1 - boot.get('alpha', 0.05)) * 100)}% CI "
            f"(seed={boot.get('seed')}, B={boot.get('n_boot')}): "
            f"**[{k.get('low')}, {k.get('high')}]**"
        )
    gate = report.get("gate_split") or "all"
    if "needs_calibration" in report:
        lines.append(
            f"- 门禁 split: **{gate}**；是否建议校准 "
            f"({gate} κ < {report.get('threshold', '?')}): "
            f"**{'是' if report['needs_calibration'] else '否'}**"
        )
    if report.get("mode"):
        lines.append(f"- 模式: `{report['mode']}`")
    if report.get("notes"):
        lines.append(f"- 说明: {report['notes']}")
    ir = report.get("inter_rater")
    if ir and ir.get("sample_size", 0) > 0:
        lines.append(
            f"- 标注者间 κ (r1 vs r2, n={ir.get('sample_size')}): **{ir.get('kappa')}**"
        )
    elif report.get("reproducibility", {}).get("second_rater_status") in (
        "pending",
        "protocol_ready",
    ):
        lines.append("- 标注者间 κ: **未报告**（第二标注者尚未写入 `human_score_r2`）")

    splits = report.get("by_split") or {}
    if splits:
        lines.extend(["", "## 分栏（dev / held_out）", ""])
        lines.append("| split | n | κ | exact | ±1 | MAE |")
        lines.append("|-------|--:|--:|------:|----:|----:|")
        for name, sub in splits.items():
            lines.append(
                f"| `{name}` | {sub.get('sample_size', 0)} | {sub.get('kappa', 0)} | "
                f"{sub.get('exact_agree_rate', 0):.1%} | {sub.get('within_one_rate', 0):.1%} | "
                f"{sub.get('mae', 0)} |"
            )
        ho = splits.get("held_out") or {}
        if ho.get("bootstrap", {}).get("kappa"):
            k = ho["bootstrap"]["kappa"]
            lines.append("")
            lines.append(
                f"- **held_out κ CI**: [{k.get('low')}, {k.get('high')}] "
                f"（优先引用此栏，勿与 protocol-tuning 的 offline 全量 κ 混谈）"
            )

    repro = report.get("reproducibility") or {}
    if repro:
        lines.extend(["", "## 可复现元数据", ""])
        for key in (
            "dataset_version",
            "rubric_boundary_version",
            "annotator_count",
            "second_rater_status",
            "judge_temperature_live",
            "random_seed_bootstrap",
            "mode",
        ):
            if key in repro or key == "mode" and report.get("mode"):
                val = repro.get(key, report.get("mode") if key == "mode" else None)
                if val is not None:
                    lines.append(f"- {key}: `{val}`")

    labels = report.get("confusion_labels") or []
    matrix = report.get("confusion") or []
    if labels and matrix:
        lines.extend(["", "## 混淆矩阵（行=Human，列=Judge）", ""])
        header = "| H\\J | " + " | ".join(str(x) for x in labels) + " |"
        sep = "|---|" + "|".join(["---"] * len(labels)) + "|"
        lines.append(header)
        lines.append(sep)
        for i, row in enumerate(matrix):
            lines.append("| " + str(labels[i]) + " | " + " | ".join(str(c) for c in row) + " |")

    pairs = report.get("pairs") or []
    if pairs:
        lines.extend(["", "## 逐条对比", "", "| id | split | human | judge | |err| |", "|---|---|---:|---:|---:|"])
        for p in pairs:
            lines.append(
                f"| {p.get('id', '')} | {p.get('split', '')} | {p.get('human', '')} | "
                f"{p.get('judge', '')} | {p.get('abs_err', '')} |"
            )

    lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 数据加载
# ──────────────────────────────────────────────


def default_calibration_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(
        os.path.join(here, "..", "dataset", "data", "calibration_human_judge.json")
    )


def load_golden_file(path: Optional[str] = None) -> list[dict[str, Any]]:
    """从 JSON 文件加载校准金标准。

    支持：
      - list[dict]
      - {"items": [...], "meta": {...}}
    """
    path = path or default_calibration_path()
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        return raw["items"]
    raise ValueError(f"无法识别校准数据格式: {path}")


def extract_judge_score(judge_result: dict[str, Any]) -> float:
    """从 JudgeExecutor / 模板输出中提取标量分。"""
    rubrics = judge_result.get("rubrics") or []
    if rubrics:
        vals = [float(r.get("score", 3)) for r in rubrics]
        return sum(vals) / len(vals)
    for key in ("step_score", "score", "judge_score"):
        if key in judge_result and judge_result[key] is not None:
            return float(judge_result[key])
    return 3.0


# ──────────────────────────────────────────────
# 校准器
# ──────────────────────────────────────────────


class JudgeCalibrator:
    """Judge 人机校准器

    用法：
        cal = JudgeCalibrator()
        cal.load_golden_file()                 # 或 load_golden(list)
        report = cal.run(mode="offline")       # 使用条目中的 judge_score
        report = cal.run(judge_fn=my_judge)    # 在线重打分
    """

    def __init__(self, threshold: float = 0.6):
        """threshold 默认 0.6：小样本下 0.7 过严，作为「建议复核」线。"""
        self.threshold = threshold
        self.golden_data: list[dict] = []
        self.source_path: Optional[str] = None

    def load_golden(self, data: list[dict]) -> None:
        self.golden_data = list(data)
        self.source_path = None

    def load_golden_file(self, path: Optional[str] = None) -> None:
        path = path or default_calibration_path()
        self.golden_data = load_golden_file(path)
        self.source_path = path

    def run(
        self,
        judge_fn: Optional[Callable[[str], dict[str, Any]]] = None,
        *,
        mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """运行校准。

        - 若提供 judge_fn：对每条 `prompt` 调用 Judge（mode=live）
        - 否则：使用条目内预填的 `judge_score`（mode=offline，可复现）
        """
        if not self.golden_data:
            return {
                "kappa": 0.0,
                "needs_calibration": True,
                "sample_size": 0,
                "error": "没有金标准数据",
                "threshold": self.threshold,
            }

        if mode is None:
            mode = "live" if judge_fn is not None else "offline"

        human_scores: list[float] = []
        judge_scores: list[float] = []
        ids: list[str] = []
        splits: list[str] = []
        dimension_pairs: dict[str, list[tuple[float, float]]] = {}
        skipped = 0
        meta_repro: dict[str, Any] = {}

        # 尝试读 meta.reproducibility（若 golden 来自文件）
        if self.source_path and os.path.isfile(self.source_path):
            try:
                with open(self.source_path, encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    meta_repro = dict((raw.get("meta") or {}).get("reproducibility") or {})
            except Exception:
                meta_repro = {}

        r1_scores: list[float] = []
        r2_scores: list[float] = []
        r12_ids: list[str] = []

        for item in self.golden_data:
            item_id = str(item.get("id", len(ids)))
            if item.get("annotation_status", "").startswith("pending"):
                skipped += 1
                continue
            human_score = item.get("human_score")
            if human_score is None:
                skipped += 1
                continue

            r2 = item.get("human_score_r2")
            if r2 is not None:
                r1_scores.append(float(human_score))
                r2_scores.append(float(r2))
                r12_ids.append(item_id)

            if judge_fn is not None:
                prompt = item.get("prompt", "")
                try:
                    judge_result = judge_fn(prompt)
                    judge_score = extract_judge_score(judge_result)
                    rubrics = judge_result.get("rubrics") or []
                except Exception:
                    skipped += 1
                    continue
            else:
                if item.get("judge_score") is None:
                    skipped += 1
                    continue
                judge_score = float(item["judge_score"])
                rubrics = item.get("judge_rubrics") or []

            human_scores.append(float(human_score))
            judge_scores.append(float(judge_score))
            ids.append(item_id)
            splits.append(str(item.get("split") or "unspecified"))

            human_rubrics = {
                r.get("dimension"): float(r.get("score", human_score))
                for r in (item.get("human_rubrics") or [])
                if r.get("dimension")
            }
            for r in rubrics:
                dim = r.get("dimension", "unknown")
                if dim not in dimension_pairs:
                    dimension_pairs[dim] = []
                h_dim = human_rubrics.get(dim, float(human_score))
                dimension_pairs[dim].append((h_dim, float(r.get("score", judge_score))))

        if not human_scores:
            return {
                "kappa": 0.0,
                "needs_calibration": True,
                "sample_size": 0,
                "error": "没有可用的人机分数对",
                "skipped": skipped,
                "threshold": self.threshold,
                "mode": mode,
            }

        table = agreement_table(human_scores, judge_scores, ids=ids)
        for i, p in enumerate(table.get("pairs") or []):
            p["split"] = splits[i] if i < len(splits) else ""

        seed = int(meta_repro.get("random_seed_bootstrap") or 20260716)
        boot = bootstrap_ci(human_scores, judge_scores, seed=seed)

        by_split: dict[str, Any] = {}
        for name in sorted(set(splits)):
            idx = [i for i, s in enumerate(splits) if s == name]
            hs = [human_scores[i] for i in idx]
            js = [judge_scores[i] for i in idx]
            sub_ids = [ids[i] for i in idx]
            sub = agreement_table(hs, js, ids=sub_ids)
            sub["bootstrap"] = bootstrap_ci(hs, js, seed=seed)
            for j, p in enumerate(sub.get("pairs") or []):
                p["split"] = name
            by_split[name] = sub

        # held_out 优先决定 needs_calibration；无则用全量
        gate_kappa = table["kappa"]
        if "held_out" in by_split and by_split["held_out"].get("sample_size", 0) > 0:
            gate_kappa = by_split["held_out"]["kappa"]

        worst_dims = []
        for dim, pairs in dimension_pairs.items():
            drifts = [j - h for h, j in pairs]
            worst_dims.append(
                {
                    "dimension": dim,
                    "n": len(pairs),
                    "avg_drift": round(sum(drifts) / len(drifts), 3),
                    "mae": round(sum(abs(d) for d in drifts) / len(drifts), 3),
                }
            )
        worst_dims.sort(key=lambda x: abs(x["avg_drift"]), reverse=True)

        report = {
            **table,
            "bootstrap": boot,
            "by_split": by_split,
            "needs_calibration": gate_kappa < self.threshold,
            "threshold": self.threshold,
            "gate_split": "held_out" if "held_out" in by_split else "all",
            "avg_human": round(sum(human_scores) / len(human_scores), 3),
            "avg_judge": round(sum(judge_scores) / len(judge_scores), 3),
            "drift": round(
                sum(judge_scores) / len(judge_scores)
                - sum(human_scores) / len(human_scores),
                3,
            ),
            "worst_dimensions": worst_dims[:5],
            "skipped": skipped,
            "mode": mode,
            "source_path": self.source_path,
            "reproducibility": {
                **meta_repro,
                "mode": mode,
            },
            "notes": (
                "offline=冻结 judge_score；live=真实 Judge。"
                "简历请优先引用 held_out 分栏 κ + CI；全量 offline κ 含协议重标样本。"
                if mode == "offline"
                else "live 模式为当次 Judge 重打分；请同时看 held_out 分栏。"
            ),
        }
        if len(r1_scores) >= 2:
            report["inter_rater"] = agreement_table(r1_scores, r2_scores, ids=r12_ids)
        else:
            report["inter_rater"] = {
                "sample_size": len(r1_scores),
                "kappa": None,
                "note": "需要至少 2 条 human_score_r2 才报告标注者间 κ",
            }
        return report


# 兼容旧文档中的示例结构
CALIBRATION_DATA_EXAMPLE = [
    {
        "id": "ex_01",
        "prompt": "评估 Agent 在步骤 1 中的表现...",
        "human_score": 4.0,
        "judge_score": 4.0,
        "human_rubrics": [
            {"dimension": "tool_selection", "score": 4, "reason": "工具选择合理"},
        ],
    },
]
