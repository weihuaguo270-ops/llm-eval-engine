"""**通用判定机制**（与任何具体评测场景无关）。

从"检索步 rubric"那条线里抽出来的可复用部分——**只保留机制，不保留该线的口径数据**：

- `verdict_for(dimension, token, bands)`：把取值映射为 ``pass`` / ``marginal`` / ``defect`` /
  ``undecidable`` / ``blank``（``blank`` **不得**当成合格）；
- `verdict_summary(cells, bands)`：一行（样本/请求）的判定计数；
- `clustered_rate_ci(...)`：**按簇聚簇**的率 CI（重采样簇而非单元——同一请求的多个检索步
  相互相关，按单元重采样会把 CI 算窄）；
- `load_bands(path)`：从 JSON 读"合格线"表（**口径数据由调用方提供**，本模块不含任何场景的判据）。

为什么这样切：一条线被撤销时，**机制应当活下来**（它换个场景照样用），
**口径数据应当随线一起走**（它是那个场景的结论，不该冒充通用件）。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

#: 不可判 token（比较时小写化；与各线的受控词表保持一致即可）
UNDECIDABLE_TOKENS = frozenset(
    {
        "na", "n/a", "none", "null", "unattr", "unattributable", "oos", "out_of_scope",
        "-", "—", "?", "不可归因", "不适用", "范围外", "同源重叠", "不标",
    }
)


def load_bands(path: Path) -> dict[str, dict[str, Any]]:
    """从 JSON 读合格线表：``{"维度": {"pass_min": 4, "marginal_min": 3, "defect": "..."}}``。"""
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verdict_for(
    dimension: str, token: Any, bands: Mapping[str, Mapping[str, Any]]
) -> str:
    """把某格取值映射为判定：``pass`` / ``marginal`` / ``defect`` / ``undecidable`` / ``blank`` / ``unbanded``。

    - ``blank``（未标）**不得**当成合格——必须进入进度信号；
    - ``undecidable`` 不进一致性统计，但**必须计入覆盖率**（不可判率本身是结论）；
    - ``unbanded`` = 该维度没有合格线（**不要把"没定义"当成"合格"**）。
    """
    raw = str(token if token is not None else "").strip().lower()
    if not raw:
        return "blank"
    band = (bands or {}).get(dimension)
    if not band:
        return "unbanded"
    if raw in UNDECIDABLE_TOKENS:
        return "undecidable"
    try:
        value = float(raw)
    except ValueError:
        return "blank"
    if value >= float(band["pass_min"]):
        return "pass"
    if value >= float(band.get("marginal_min", band["pass_min"])):
        return "marginal"
    return "defect"


def verdict_summary(
    cells: Mapping[str, Any], bands: Mapping[str, Mapping[str, Any]]
) -> dict[str, int]:
    """把一行（一个样本/请求）的取值汇总成**判定计数**。"""
    counts: dict[str, int] = {}
    for dimension, token in (cells or {}).items():
        if str(dimension).startswith("_"):
            continue
        key = verdict_for(str(dimension), token, bands)
        counts[key] = counts.get(key, 0) + 1
    return counts


def clustered_rate_ci(
    defects: Mapping[str, int],
    totals: Mapping[str, int],
    n_boot: int = 2000,
    seed: int = 20261003,
) -> tuple[float, float]:
    """**按簇聚簇**的率 CI：重采样**簇**（如请求），再算率。

    :param defects: 簇 → 该簇内的缺陷数
    :param totals: 簇 → 该簇内可判单元数
    :return: (2.5%, 97.5%) 百分位区间；样本不足时返回 (nan, nan)
    """
    keys = list(totals)
    if not keys or sum(totals.values()) == 0:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    rates: list[float] = []
    for _ in range(n_boot):
        picked = [keys[rng.randrange(len(keys))] for _ in keys]
        total = sum(totals[k] for k in picked)
        if not total:
            continue
        rates.append(sum(defects.get(k, 0) for k in picked) / total)
    if not rates:
        return (float("nan"), float("nan"))
    rates.sort()
    return (rates[int(0.025 * len(rates))], rates[int(0.975 * len(rates)) - 1])


__all__ = [
    "UNDECIDABLE_TOKENS",
    "clustered_rate_ci",
    "load_bands",
    "verdict_for",
    "verdict_summary",
]
