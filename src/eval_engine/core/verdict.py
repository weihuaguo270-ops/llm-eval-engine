"""**通用判定机制**（与任何具体评测场景无关）。

从"检索步 rubric"那条线里抽出来的可复用部分——**只保留机制，不保留该线的口径数据**：

- `verdict_for(dimension, token, bands)`：把取值映射为 ``pass`` / ``marginal`` / ``defect`` /
  ``undecidable`` / ``blank``（``blank`` **不得**当成合格）；
- `verdict_summary(cells, bands)`：一行（样本/请求）的判定计数；
- `clustered_rate_ci(...)`：**按簇聚簇**的率 CI（重采样簇而非单元——同一请求的多个检索步
  相互相关，按单元重采样会把 CI 算窄）；
- `load_bands(path)`：只取「维度 → 档位」那一层（**口径数据由调用方提供**，本模块不含任何场景的口径数据）；
- `load_bands_document(path)`：读整份合格线文档（含 `provenance` / `derivation` 等元数据——
  **丢掉元数据等于丢掉可追溯性**）；
- `bands_identity(path)`：合格线的**内容身份**（对维度层做规范化后取 sha256）——
  **只算、只记录**；是否据此阻断由门禁侧决定。

为什么这样切：一条线被撤销时，**机制应当活下来**（它换个场景照样用），
**口径数据应当随线一起走**（它是那个场景的结论，不该冒充通用件）。
"""

from __future__ import annotations

import hashlib
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


#: 合格线文件里承载「维度 → 档位」的**两种外壳键**。两种都在真实文件里出现过，
#: 而按哪一种解析会**改变判定结果**——实测：同一份内容、同一个 5 分，
#: 外壳键 ``bands`` 读成 ``unbanded``、``verdict_bands`` 读成 ``pass``，**只差一个键名**。
#: 故必须一并认。
#:
#: - ``bands``：被跟踪的 ``dataset/data/verdict_bands_line1.json``（另有 ``provenance`` / ``derivation``）
#: - ``verdict_bands``：批次本地 ``verdict_bands.json``（另有 ``note`` / ``rulings_version`` / ``convention``）
BANDS_WRAPPER_KEYS = ("bands", "verdict_bands")


def _looks_like_band(value: Any) -> bool:
    """一条合格线**必须**含 ``pass_min``（`verdict_for` 直接取它，没有它就没法判档）。

    用它把"元数据"与"维度"分开：外壳文件里的 ``provenance`` / ``derivation`` / ``note``
    会被当成维度，而真正的维度全部落空——**且返回值非空，调用方那句
    「未加载到任何合格线」的告警不会触发**（实测就是这样静默的）。
    """
    return isinstance(value, Mapping) and "pass_min" in value


def load_bands_document(path: Path) -> dict[str, Any]:
    """读**整份**合格线文档（含 ``provenance`` / ``derivation`` 等元数据）。

    读不到、不是 JSON 对象、解析失败 → ``{}``。与 `load_bands` 分开的理由：
    要口径出处的调用方必须能拿到元数据，**只取维度层会把可追溯性丢掉**。
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def load_bands(path: Path) -> dict[str, dict[str, Any]]:
    """只取「维度 → 档位」那一层，交给 `verdict_for` 用。

    **兼容三种真实外形**：

    - 外壳键 ``bands``（被跟踪的 ``verdict_bands_line1.json``，另一份加载器只认这一种）
    - 外壳键 ``verdict_bands``（批次本地的 ``verdict_bands.json``）
    - 扁平：整份文档就是维度表

    外壳里的 ``provenance`` / ``derivation`` / ``note`` / ``rulings_version`` / ``convention``
    是**元数据、不是维度**，故不入返回值；要元数据用 `load_bands_document`。

    兜底那条**只收像合格线的条目**（含 ``pass_min``）。旧实现把整份文档都收下，
    于是外壳文件的元数据被当成维度、真维度全部落空 → 一律 ``unbanded``，**而且不报错**
    （实测踩过：整批缺陷率全 0，只因"没算"被读成了"零缺陷"）。
    """
    document = load_bands_document(path)
    for key in BANDS_WRAPPER_KEYS:
        inner = document.get(key)
        if isinstance(inner, Mapping):
            return {str(k): dict(v) for k, v in inner.items() if _looks_like_band(v)}
    return {str(k): dict(v) for k, v in document.items() if _looks_like_band(v)}


#: 合格线**内容身份**的算法标识。写进报告，供日后比对时确认"两边算的是同一种身份"。
#:
#: 语义：对**维度层**（`load_bands` 的返回值）做规范化 JSON 后再取 sha256。
#: **不覆盖** ``provenance`` / ``derivation`` / ``note`` / ``rulings_version`` 等元数据——
#: 它们是说明、不是判定标准：**改一句注释不该产生漂移告警，改一个档位必须产生**。
BANDS_IDENTITY_ALGO = "sha256:canonical-json-of-dimensions/v1"


def canonical_bands_bytes(bands: Mapping[str, Mapping[str, Any]]) -> bytes:
    """把维度层序列化成**稳定字节**：键有序、分隔符固定、UTF-8。

    **已知边界**（写在这里而不是藏着）：这是**字节级**身份，不做数值归一化——
    JSON 里写 ``4`` 与 ``4.0`` 会得到不同身份。判档用的是 ``float()``，两者语义相同，
    故它只会在有人手工改写法时误报；要消除需先定"数值规范形"，属后续决定。
    """
    canonical = json.dumps(
        {str(key): dict(value) for key, value in bands.items()},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return canonical.encode("utf-8")


def bands_identity(path: Path) -> dict[str, Any]:
    """合格线的**内容身份**（P1：只算、只记录；**是否据此阻断由门禁侧决定**）。

    返回字段：

    - ``algo``：算法标识（`BANDS_IDENTITY_ALGO`）；
    - ``sha256``：身份；``None`` 表示**没有可识别的合格线**；
    - ``dimensions``：参与身份计算的维度名（有序）；
    - ``recognized``：是否存在可识别的合格线——``False`` 时判定会**全落成** `unbanded`；
    - ``reason``：``recognized=False`` 的原因，取值只有两种：

      - ``unreadable``：读不到 / 解析失败 / 不是 JSON 对象；
      - ``no_recognizable_bands``：读到了，但**一条像合格线的条目都没有**
        （含元数据却不含 ``pass_min`` 的文档即属此类）。

    **冲突语义**（身份与内容不符、两版并存）**不在本函数**——那是读取端与门禁侧的事
    （见 `docs/VERDICT_IDENTITY_PLAN.md` 的 P2/P3）。
    """
    document = load_bands_document(path)
    bands = load_bands(path)
    identity: dict[str, Any] = {
        "algo": BANDS_IDENTITY_ALGO,
        "sha256": None,
        "dimensions": sorted(bands),
        "recognized": False,
        "reason": None,
    }
    if not bands:
        identity["reason"] = "unreadable" if not document else "no_recognizable_bands"
        return identity
    identity["sha256"] = hashlib.sha256(canonical_bands_bytes(bands)).hexdigest()
    identity["recognized"] = True
    return identity


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
    "BANDS_IDENTITY_ALGO",
    "BANDS_WRAPPER_KEYS",
    "UNDECIDABLE_TOKENS",
    "bands_identity",
    "canonical_bands_bytes",
    "clustered_rate_ci",
    "load_bands",
    "load_bands_document",
    "verdict_for",
    "verdict_summary",
]
