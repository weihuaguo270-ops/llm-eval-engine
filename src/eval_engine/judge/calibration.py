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
    if "needs_calibration" in report:
        lines.append(
            f"- 是否建议校准 (κ < {report.get('threshold', '?')}): "
            f"**{'是' if report['needs_calibration'] else '否'}**"
        )
    if report.get("mode"):
        lines.append(f"- 模式: `{report['mode']}`")
    if report.get("notes"):
        lines.append(f"- 说明: {report['notes']}")

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
        lines.extend(["", "## 逐条对比", "", "| id | human | judge | |err| |", "|---|---:|---:|---:|"])
        for p in pairs:
            lines.append(
                f"| {p.get('id', '')} | {p.get('human', '')} | {p.get('judge', '')} | {p.get('abs_err', '')} |"
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
        dimension_pairs: dict[str, list[tuple[float, float]]] = {}
        skipped = 0

        for item in self.golden_data:
            item_id = str(item.get("id", len(ids)))
            human_score = item.get("human_score")
            if human_score is None:
                skipped += 1
                continue

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
            "needs_calibration": table["kappa"] < self.threshold,
            "threshold": self.threshold,
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
            "notes": (
                "offline 使用数据集内冻结的 judge_score，便于 CI/复现；"
                "live 需配置 Judge API Key 后重打分。"
                if mode == "offline"
                else "live 模式为当次 Judge 重打分结果。"
            ),
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
