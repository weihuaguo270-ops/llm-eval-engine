"""search_calibration — 检索步维度的**独立** κ 分栏

为什么必须单独一栏
------------------
``docs/METRICS_TRUST.md`` 把多模态主钉的 κ 单位**钉死**为
``dimension_cell = episode × media/final step × dimension``。把检索步维度并进
那一栏会改变 κ 的分母定义，等于同时作废旧证据与新证据。因此检索步走独立分栏：

    kappa_unit = search_dimension_cell = episode × search step × dimension

单独报 cell n、单独报 bootstrap CI、单独报 gate_split；**禁止**与文本 Judge κ
或多模态 dimension_cell 合成"一个总分"。

当前状态
--------
**uncalibrated**（缺 held-out 人工校准样本）。在补齐之前不得引用任何 κ 数值。
与媒体分栏不同，本模块在无样本时返回 ``status="uncalibrated"`` 而不是 ``None``：
分栏的存在本身需要可见，否则"没做"和"做了但没有数据"无法区分。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from eval_engine.core.search_step import SEARCH_DIMENSIONS
from eval_engine.judge.calibration import agreement_table, bootstrap_ci

SEARCH_KAPPA_UNIT = "search_dimension_cell"
SEARCH_KAPPA_UNIT_NOTE = (
    "Cohen's kappa over held-out search-step dimension cells "
    "(episode x search step x dimension); separate from the media/final "
    "dimension_cell pin — do not merge the two columns."
)
SEARCH_GATE_SPLIT = "held_out"
SEARCH_KAPPA_THRESHOLD = 0.6
STATUS_UNCALIBRATED = "uncalibrated"
STATUS_CALIBRATED = "calibrated"

_UNCALIBRATED_NOTE = (
    "无 held-out 检索步校准样本：本栏不得引用任何 κ 数值。"
    "补齐后另写 calibration_snapshot_YYYYMMDD_search_*.md，不要改写本行状态之外的口径。"
)


def _split_rows(
    rows: Optional[Sequence[Mapping[str, Any]]],
) -> tuple[list[Mapping[str, Any]], list[str]]:
    """挑出 held-out 检索步样本；把串栏的行单独返回以便报错。"""
    kept: list[Mapping[str, Any]] = []
    foreign: list[str] = []
    for row in rows or []:
        if row.get("split") != SEARCH_GATE_SPLIT:
            continue
        dimension = row.get("dimension")
        if dimension not in SEARCH_DIMENSIONS:
            foreign.append(str(dimension))
            continue
        if row.get("human_score") is None or row.get("judge_score") is None:
            continue
        kept.append(row)
    return kept, foreign


def search_calibration_column(
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """构造检索步分栏。

    rows 为 ``run_calibration`` 风格的行：``episode_id / step_index / dimension /
    split / human_score / judge_score / id``（可选）。只有 ``split="held_out"`` 且
    ``dimension`` 属于 :data:`SEARCH_DIMENSIONS` 的行会进入本栏。

    传入别的维度的 held-out 行会直接抛 ``ValueError``——这是防止两栏被悄悄合并的
    结构性约束，不是可以绕过的告警。
    """
    kept, foreign = _split_rows(rows)
    if foreign:
        raise ValueError(
            "search_calibration_column 收到非检索步维度: "
            f"{sorted(set(foreign))}；这些行属于 dimension_cell 主钉，"
            "两栏不得混算。"
        )

    base: dict[str, Any] = {
        "kappa_unit": SEARCH_KAPPA_UNIT,
        "kappa_unit_note": SEARCH_KAPPA_UNIT_NOTE,
        "dimensions": list(SEARCH_DIMENSIONS),
        "gate_split": SEARCH_GATE_SPLIT,
        "threshold": SEARCH_KAPPA_THRESHOLD,
    }

    if not kept:
        return {
            **base,
            "status": STATUS_UNCALIBRATED,
            "n": 0,
            "kappa": None,
            "bootstrap": None,
            "episode_ids": [],
            "episode_count": 0,
            "needs_calibration": None,
            "by_split": {},
            "notes": _UNCALIBRATED_NOTE,
        }

    humans = [float(row["human_score"]) for row in kept]
    judges = [float(row["judge_score"]) for row in kept]
    ids = [
        str(
            row.get("id")
            or f"{row.get('episode_id')}-{row.get('step_index')}-{row.get('dimension')}"
        )
        for row in kept
    ]
    table = agreement_table(humans, judges, ids=ids)
    boot = bootstrap_ci(humans, judges)
    kappa = float(table["kappa"])
    episode_ids = sorted({str(row.get("episode_id")) for row in kept})

    return {
        **base,
        **table,
        "status": STATUS_CALIBRATED,
        "n": len(kept),
        "bootstrap": boot,
        "by_split": {SEARCH_GATE_SPLIT: {**table, "bootstrap": boot}},
        "episode_ids": episode_ids,
        "episode_count": len(episode_ids),
        "needs_calibration": kappa < SEARCH_KAPPA_THRESHOLD,
        "notes": (
            "检索步分栏：与 dimension_cell 主钉分栏引用；报 cell n 与 episode_count "
            "各自的值，不合成总分。n 较小时 κ 的 CI 会明显变宽，只作趋势证据。"
        ),
    }
