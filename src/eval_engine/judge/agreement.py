"""有序量表的一致性统计（**L2 测量层**）。

本模块补齐两个行业标准件，与既有的 `cohens_kappa`（**未加权**）**并列**，不替换：

1. **加权 κ**（Cohen 1968）——1–5 是**有序**量表，"1 vs 2"与"1 vs 5"不应同等计罚。
   线性权重 ``w = |i-j|/(k-1)``；二次权重 ``w = (|i-j|/(k-1))²``。
2. **Krippendorff α**（Krippendorff 2011）——支持**多标注者**与**缺失值**，可指定
   ``nominal`` / ``ordinal`` / ``interval`` 度量；有序度量下相邻分歧只受小罚。
3. **配对置换检验**（paired permutation）——同一样本上比较**两个版本**（或两位标注者）是否显著不同；
   仅报 CI 无法回答"A 版是否优于 B 版"。

为什么需要：未加权 κ 把相邻分歧与跨档分歧同等处理，且对**边际分布偏斜**敏感
（本仓 held_out 有约一半是 5 分）→ 单一未加权 κ 不足以支撑对外结论。

参考：
- Cohen, J. (1968). Weighted kappa. *Psychological Bulletin*, 70(4), 213–220.
- Krippendorff, K. (2011). Computing Krippendorff's Alpha-Reliability.
- 配对置换检验：见任何配对设计的非参数检验教材（H0 下逐样本可交换）。
"""

from __future__ import annotations

import random
from typing import Iterable, Optional, Sequence

__all__ = [
    "krippendorff_alpha",
    "ordinal_agreement",
    "paired_permutation_kappa",
    "weighted_kappa",
]


def ordinal_agreement(
    human: Sequence[float],
    other: Sequence[float],
    *,
    scale_min: int = 1,
    scale_max: int = 5,
) -> dict:
    """把一列有序评分的一致性**成套**报出来（与未加权 κ **并列**，不替换）。

    为什么并列：既有的 ``cohens_kappa`` 是**未加权**的（历史口径），而 1–5 是**有序**量表——
    标准统计是加权 κ 或 Krippendorff α。只报一个数，会让外部复算者得到不同结果，
    从而不可比。**引用时必须带统计量与权重。**
    """
    from eval_engine.judge.calibration import cohens_kappa  # 延迟导入，避免循环依赖

    units = [[a, b] for a, b in zip(human, other)]
    n = len(units)
    exact = sum(1 for a, b in zip(human, other) if a == b)
    within_one = sum(1 for a, b in zip(human, other) if abs(a - b) <= 1)
    return {
        "n": n,
        "kappa_unweighted": cohens_kappa(list(human), list(other)),
        "kappa_linear": weighted_kappa(human, other, weights="linear", scale_min=scale_min, scale_max=scale_max),
        "kappa_quadratic": weighted_kappa(human, other, weights="quadratic", scale_min=scale_min, scale_max=scale_max),
        "alpha_ordinal": krippendorff_alpha(units, level="ordinal"),
        "exact_rate": round(exact / n, 4) if n else 0.0,
        "within_one_rate": round(within_one / n, 4) if n else 0.0,
        "_note": "未加权 κ 为历史口径；线性/二次加权 κ 与 α(ordinal) 为有序量表标准统计；四者不可混比。",
    }


def _confusion(
    a: Sequence[float], b: Sequence[float], scale_min: int, scale_max: int
) -> tuple[list[list[int]], int]:
    labels = list(range(scale_min, scale_max + 1))
    index = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    matrix = [[0] * k for _ in range(k)]
    n = 0
    for x, y in zip(a, b):
        i, j = index.get(int(round(x))), index.get(int(round(y)))
        if i is None or j is None:
            continue
        matrix[i][j] += 1
        n += 1
    return matrix, n


def weighted_kappa(
    a: Sequence[float],
    b: Sequence[float],
    *,
    weights: str = "linear",
    scale_min: int = 1,
    scale_max: int = 5,
) -> float:
    """加权 Cohen κ（有序量表）。``weights`` ∈ {``linear``, ``quadratic``}。"""
    if weights not in ("linear", "quadratic"):
        raise ValueError("weights 只能是 linear / quadratic")
    matrix, n = _confusion(a, b, scale_min, scale_max)
    if n == 0:
        return 0.0
    k = scale_max - scale_min + 1
    row = [sum(r) for r in matrix]
    col = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    expected = [[row[i] * col[j] / n for j in range(k)] for i in range(k)]

    def penalty(i: int, j: int) -> float:
        d = abs(i - j) / (k - 1)
        return d if weights == "linear" else d * d

    observed_disagree = sum(penalty(i, j) * matrix[i][j] for i in range(k) for j in range(k))
    expected_disagree = sum(penalty(i, j) * expected[i][j] for i in range(k) for j in range(k))
    if expected_disagree == 0:
        return 1.0
    return round(1.0 - observed_disagree / expected_disagree, 4)


def _ordinal_delta(counts: Sequence[int], c: int, k: int) -> float:
    """有序度量的 δ²（Krippendorff 2011）：``counts`` 按**秩**索引。

    δ²(c,k) = ( Σ_{g=c..k} n_g − (n_c + n_k)/2 )² —— 跨过的档越多、且这些档越"密集"，罚越重。
    """
    lo, hi = (c, k) if c <= k else (k, c)
    total = sum(counts[g] for g in range(lo, hi + 1))
    return (total - (counts[lo] + counts[hi]) / 2.0) ** 2


def krippendorff_alpha(
    units: Iterable[Sequence[Optional[float]]],
    *,
    level: str = "ordinal",
) -> float:
    """Krippendorff α。``units`` = 每个样本的**各标注者取值**（缺失用 ``None``）。

    ``level`` ∈ {``nominal``, ``ordinal``, ``interval``}。支持每样本标注者数不同（缺失值）。
    """
    units = [list(u) for u in units]
    values = sorted({v for u in units for v in u if v is not None})
    if len(values) < 2:
        return 1.0
    ranks = {v: i for i, v in enumerate(values)}
    counts: dict[int, int] = {i: 0 for i in range(len(values))}

    # 同时矩阵 o_ck（Krippendorff 2011 的算法）
    k_n = len(values)
    o = [[0.0] * k_n for _ in range(k_n)]
    for u in units:
        present = [v for v in u if v is not None]
        m = len(present)
        if m < 2:
            continue
        for i, vi in enumerate(present):
            counts[ranks[vi]] += 1
            for j, vj in enumerate(present):
                if i == j:
                    continue
                o[ranks[vi]][ranks[vj]] += 1.0 / (m - 1)

    n = sum(counts.values())
    if n < 2:
        return 0.0
    marginal = [counts[i] for i in range(k_n)]

    def delta(c: int, k: int) -> float:
        if level == "nominal":
            return 0.0 if c == k else 1.0
        if level == "interval":
            return (values[c] - values[k]) ** 2
        return _ordinal_delta([counts[i] for i in range(k_n)], c, k)

    do = sum(o[c][k] * delta(c, k) for c in range(k_n) for k in range(k_n))
    de = sum(marginal[c] * marginal[k] * delta(c, k) for c in range(k_n) for k in range(k_n))
    if de == 0:
        return 1.0
    return round(1.0 - (do * (n - 1)) / de, 4)


def paired_permutation_kappa(
    human: Sequence[float],
    version_a: Sequence[float],
    version_b: Sequence[float],
    *,
    n_perm: int = 2000,
    seed: int = 20261004,
    statistic=weighted_kappa,
) -> dict:
    """配对置换检验：两版 scores 在同一批样本上是否显著不同（H0：逐样本可交换）。

    返回观测差（b−a）、置换分布的双侧 p 值、以及置换分布的分位数。
    """
    if not (len(human) == len(version_a) == len(version_b)):
        raise ValueError("三列长度必须一致（配对设计）")
    observed = statistic(human, version_b) - statistic(human, version_a)
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_perm):
        swapped_a, swapped_b = [], []
        for x, y in zip(version_a, version_b):
            if rng.random() < 0.5:
                swapped_a.append(x)
                swapped_b.append(y)
            else:
                swapped_a.append(y)
                swapped_b.append(x)
        deltas.append(statistic(human, swapped_b) - statistic(human, swapped_a))
    extreme = sum(1 for d in deltas if abs(d) >= abs(observed))
    p = (extreme + 1) / (n_perm + 1)
    deltas.sort()
    return {
        "observed_delta": round(observed, 4),
        "p_value": round(p, 4),
        "perm_ci_low": round(deltas[int(0.025 * n_perm)], 4),
        "perm_ci_high": round(deltas[int(0.975 * n_perm) - 1], 4),
        "n_perm": n_perm,
    }
