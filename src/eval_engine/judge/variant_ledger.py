"""口径变体的**选择防护**：同一 batch 不得第二次用于"选择口径"。

## 规则（同时写进 `docs/EVAL_DESIGN.md` §3.3）

> **同一 batch 上不得第二次用于选择口径** —— 即：不得在同一批样本上比较第二个口径变体并据此采纳。

判定细则：

| 情形 | 处置 |
|---|---|
| 同一份口径指纹**重复**运行（对照 / 复现 / 抖动测量） | **允许**（重复不是新变体） |
| 用途标为 ``probe``（**故意造坏**的对照，用于验证"指标能否检出"） | **允许**，但记为 probe（它不产生"采纳哪个口径"的选择） |
| 同一 batch 上出现**第二个不同指纹**且用途为 ``adopt`` | **默认拒绝** |
| 上一条确需运行 | 必须显式 ``--allow-selection`` / ``JUDGE_ALLOW_SELECTION=1``；该次读数标记为 **selection_use=true，不得用于采纳** |

## 这个检查的性质（必须诚实写清）

它是给**下一个没有记忆的执行者**的减速带，**不是安全控制**：
当作者与执行者是同一个 agent 时，它可以被绕过——本仓库的历史上已经发生过。
它的价值在于：新会话不会带着"这批已经被用过"的记忆，
因此**只有留在仓库里的规则与检查**才拦得住重复。

## 账本

`src/eval_engine/dataset/data/rubric_variant_ledger.json`（**入库跟踪**，随仓库分发——
否则新克隆看不到历史，检查就形同虚设）。账本只记录"某批上跑过哪些口径指纹"，
**不**对任何批次作证据地位判定。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = _ROOT / "dataset" / "data" / "rubric_variant_ledger.json"

__all__ = [
    "LEDGER_PATH",
    "batch_key",
    "check_and_record",
    "evaluate",
    "load_ledger",
    "record",
    "save_ledger",
]

FINGERPRINT_PLACEHOLDER = "unknown"


def batch_key(dataset_id: Optional[str], dataset_version: Any, split: Optional[str]) -> str:
    """批次标识：``<dataset_id>@v<version>/<split>``（split 为空时记为 all）。"""
    return f"{dataset_id or 'unknown'}@v{dataset_version if dataset_version is not None else '?'}/{split or 'all'}"


def load_ledger() -> dict[str, Any]:
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return {"_note": "口径变体账本：记录『某批上跑过哪些口径指纹』。规则见 judge/variant_ledger.py 与 EVAL_DESIGN §3.3。",
            "batches": {}}


def save_ledger(ledger: dict[str, Any]) -> None:
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def evaluate(
    batch: str,
    fingerprint: str,
    *,
    purpose: str = "adopt",
    allow_selection: bool = False,
    ledger: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """**纯判定**（不写账本）：是否允许在该 batch 上运行这个口径指纹。"""
    data = ledger if ledger is not None else load_ledger()
    prior = ((data.get("batches") or {}).get(batch) or {}).get("fingerprints") or {}
    known = fingerprint in prior

    if known:
        return {"allowed": True, "selection": False, "reason": "同指纹重复运行（对照/复现），不是新变体",
                "prior": sorted(prior)}
    if purpose == "probe":
        return {"allowed": True, "selection": False,
                "reason": "用途=probe（故意造坏的对照，用于验证指标灵敏度），不构成『选择口径』",
                "prior": sorted(prior)}
    if not prior:
        return {"allowed": True, "selection": False, "reason": "该批上的第一个 adopt 口径指纹", "prior": []}
    if allow_selection:
        return {"allowed": True, "selection": True,
                "reason": "**显式承担**：同一批上的第二个口径变体 → 该次读数标记 selection_use，不得用于采纳",
                "prior": sorted(prior)}
    return {
        "allowed": False,
        "selection": False,
        "reason": ("同一批上已存在另一份口径指纹 —— 再跑一个**不同**指纹即构成『在同一批上选择口径』。\n"
                   "  规则：同一 batch 不得第二次用于选择口径（EVAL_DESIGN §3.3）。\n"
                   "  可选出路：① 换新样本（正解）；② 若确为故意造坏的指标验证，设 JUDGE_VARIANT_PURPOSE=probe；\n"
                   "  ③ 若确实要承担后果，加 --allow-selection（该次读数将被标记为选择产物）。"),
        "prior": sorted(prior),
    }


def record(
    batch: str,
    fingerprint: str,
    *,
    purpose: str = "adopt",
    selection: bool = False,
    stamp: Optional[str] = None,
) -> dict[str, Any]:
    """把本次运行写入账本（幂等：同指纹只累加计数）。"""
    ledger = load_ledger()
    batches = ledger.setdefault("batches", {})
    entry = batches.setdefault(batch, {"fingerprints": {}})
    fps = entry.setdefault("fingerprints", {})
    today = stamp or datetime.now().strftime("%Y-%m-%d")
    rec = fps.setdefault(fingerprint, {"first_seen": today, "runs": 0, "purposes": [], "selection_use": False})
    rec["runs"] += 1
    rec["last_seen"] = today
    if purpose not in rec["purposes"]:
        rec["purposes"].append(purpose)
    rec["selection_use"] = bool(rec["selection_use"] or selection)
    save_ledger(ledger)
    return rec


def check_and_record(
    batch: str,
    fingerprint: str,
    *,
    purpose: str = "adopt",
    allow_selection: bool = False,
) -> dict[str, Any]:
    """判定 + （允许时）记账。返回判定结果，含 ``allowed`` / ``selection`` / ``reason``。"""
    decision = evaluate(batch, fingerprint, purpose=purpose, allow_selection=allow_selection)
    if decision["allowed"]:
        decision["record"] = record(batch, fingerprint, purpose=purpose, selection=decision["selection"])
    return decision
