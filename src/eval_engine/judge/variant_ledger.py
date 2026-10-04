"""口径变体的**选择防护**（配额 = 每批一次 adopt 级对照）。

## 规则（同时写进 `docs/EVAL_DESIGN.md` §3.3）

每批样本最多出现 **两个 adopt 口径指纹**：**一个基线 + 一个对照**。

| 情形 | 处置 | 消耗配额 |
|---|---|---|
| 该批**尚无基线**，本次为 ``adopt`` | 记为 **baseline**，允许 | 否（基线可重复跑：复现 / 抖动） |
| 已有基线，本次指纹 == 基线 | 允许（重复基线） | 否 |
| 已有基线，本次指纹 ≠ 基线，**配额未用** | 允许一次，记为 **comparison** 臂 | **是** |
| 配额已用，本次指纹 == comparison 臂 | 允许（同一臂复现） | 否 |
| 配额已用，出现**第三个**不同 adopt 指纹 | **拒绝**（退出码 2，在调用 Judge LLM **之前**） | — |
| ``JUDGE_VARIANT_PURPOSE=probe``（故意造坏的对照） | 允许，记为 probe | 否 |
| ``JUDGE_ALLOW_SELECTION=1``（逃生口） | 允许，但报告写 ``selection_use: true``，**不得用于采纳** | 否 |

## 预注册强制（配额内那次对照的真正护栏）

**comparison 臂必须先有一份预注册文件**，否则**拒绝**。默认路径
`dataset/data/prereg/<batch>_<variant_sha16>.json`，可用 ``--prereg <file>`` 覆盖。

预注册必须写明：预测方向/幅度、采纳判据、负结果处置、写就时间（``frozen_at``），
并且 ``variant_sha16`` 要**绑定到本次要跑的那个指纹**（否则预注册与实验对不上）。

账本记录该文件的 **sha256**；此后这个臂再复现时会重算 sha256，
**对不上就拒绝**——于是"先写预注册、之后不得修改"是机器强制的，不是口头承诺。

预注册为什么放在 `dataset/data/`（随仓库分发）而不是 `reports/`：
`reports/` 在 `.gitignore` 里，放那儿等于预注册进不了仓库、外部无法验证它早于那次运行。

## 这个检查的性质（必须诚实写清）

它是给**没有记忆的下一个执行者**的减速带，**不是安全控制**：
当作者与执行者是同一个 agent 时，它可以被绕过——本仓库的历史上已经发生过。
它的价值在于：新会话不会带着"这批已经被用过"的记忆，
因此**只有留在仓库里的规则与检查**才拦得住重复。

**已知不完备**（改成本配额语义后依然成立，甚至更重要）：

1. 它拦的是"同一批上的**第三个** adopt 指纹"，拦不住"第一次就直接用变体"；
2. ``probe`` 与 ``JUDGE_ALLOW_SELECTION=1`` 都是**故意留的出口**：
   前者假设"故意造坏"、后者把读数标成不可采纳，但**都要靠人诚实**——
   把真变体标成 probe 仍然能跑，只是不该被引用；
3. **配额是"每批"的，不是"每批每目标"的**：一次对照用掉之后，
   这一批就不能再用来回答任何别的口径问题。
4. ``selection`` 与 ``probe`` 的读数**不占配额**（它们不能用于采纳），
   因此"跑了几个不可采纳的读数"不会挤压那次真正的对照——
   真正稀缺的始终是**可采纳的那一次**。

## 账本

`src/eval_engine/dataset/data/rubric_variant_ledger.json`（**入库跟踪**，随仓库分发——
否则新克隆看不到历史，检查就形同虚设）。账本记录"某批上跑过哪些口径指纹、各自什么角色、
配额用没用、那次对照绑的是哪份预注册"，**不**对任何批次作证据地位判定。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = _ROOT / "dataset" / "data" / "rubric_variant_ledger.json"
#: 预注册目录。**必须在入库跟踪的路径下**（`reports/` 被 .gitignore 忽略），
#: 否则预注册进不了仓库，外部无法验证"它早于那次 live 运行"。
PREREG_DIR = _ROOT / "dataset" / "data" / "prereg"

__all__ = [
    "LEDGER_PATH",
    "PREREG_DIR",
    "batch_key",
    "check_and_record",
    "evaluate",
    "ledger_file",
    "load_ledger",
    "prereg_path",
    "record",
    "save_ledger",
    "validate_prereg",
]

FINGERPRINT_PLACEHOLDER = "unknown"

ROLE_BASELINE = "baseline"
ROLE_COMPARISON = "comparison"
ROLE_PROBE = "probe"
ROLE_SELECTION = "selection"
_ADOPT_ROLES = (ROLE_BASELINE, ROLE_COMPARISON)

#: 预注册里必须非空的文本字段（缺任一条即拒绝）。
_PREREG_TEXT_FIELDS = (
    "hypothesis",
    "predicted_direction",
    "negative_result_action",
)
_PREREG_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
)


# ──────────────────────────────────────────────
# 批次与路径
# ──────────────────────────────────────────────


def batch_key(dataset_id: Optional[str], dataset_version: Any, split: Optional[str]) -> str:
    """批次标识：``<dataset_id>@v<version>/<split>``（split 为空时记为 all）。"""
    return f"{dataset_id or 'unknown'}@v{dataset_version if dataset_version is not None else '?'}/{split or 'all'}"


def _slug(text: str) -> str:
    """把批次标识变成文件名安全的片段（``@`` ``.`` ``-`` ``_`` 保留）。"""
    return "".join(c if (c.isalnum() or c in "._@-") else "_" for c in str(text))


def prereg_path(batch: str, fingerprint: str) -> Path:
    """默认预注册路径：``<PREREG_DIR>/<batch>_<variant_sha16>.json``。"""
    return PREREG_DIR / f"{_slug(batch)}_{fingerprint}.json"


# ──────────────────────────────────────────────
# 账本读写
# ──────────────────────────────────────────────


def ledger_file() -> Path:
    """账本实际路径；``JUDGE_VARIANT_LEDGER`` 可指向别处（测试隔离 / 多批并行）。"""
    override = os.environ.get("JUDGE_VARIANT_LEDGER", "").strip()
    return Path(override) if override else LEDGER_PATH


def load_ledger() -> dict[str, Any]:
    path = ledger_file()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "_note": (
            "口径变体账本：记录『某批上跑过哪些口径指纹、各自什么角色（baseline/comparison/probe/selection）、"
            "adopt 配额用没用、那次对照绑的是哪份预注册』。规则见 judge/variant_ledger.py 与 docs/EVAL_DESIGN.md §3.3。"
        ),
        "batches": {},
    }


def save_ledger(ledger: dict[str, Any]) -> None:
    path = ledger_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_arm(first_seen: Optional[str]) -> dict[str, Any]:
    return {
        "roles": [],
        "first_seen": first_seen,
        "last_seen": first_seen,
        "runs": 0,
        "purposes": [],
        "selection_use": False,
        "prereg": None,
    }


def _migrate_legacy(entry: dict[str, Any]) -> None:
    """把旧 schema 的 ``fingerprints`` 折进 ``arms``（旧账本没有角色/配额概念）。

    保守处理：按登记顺序把 adopt 指纹当作「基线 + 一次对照」，即视**配额已用**——
    宁可拦住，也不放过。
    """
    legacy = entry.pop("fingerprints", None)
    if not isinstance(legacy, dict):
        return
    arms: dict[str, Any] = entry.setdefault("arms", {})
    adopt_fps: list[str] = []
    for fingerprint, raw in legacy.items():
        rec = raw if isinstance(raw, dict) else {}
        purposes = [str(p).lower() for p in (rec.get("purposes") or [])]
        probe_only = bool(purposes) and all(p == ROLE_PROBE for p in purposes)
        if probe_only:
            role: Optional[str] = ROLE_PROBE
        elif len(adopt_fps) == 0:
            role = ROLE_BASELINE
        elif len(adopt_fps) == 1:
            role = ROLE_COMPARISON
        else:
            role = ROLE_SELECTION
        if role != ROLE_PROBE:
            adopt_fps.append(fingerprint)
        arm = arms.setdefault(fingerprint, _new_arm(rec.get("first_seen")))
        if role not in arm["roles"]:
            arm["roles"].append(role)
        arm["runs"] = int(arm.get("runs") or 0) + int(rec.get("runs") or 0)
        arm["last_seen"] = rec.get("last_seen") or arm.get("last_seen") or arm.get("first_seen")
        for purpose in purposes:
            if purpose not in arm["purposes"]:
                arm["purposes"].append(purpose)
        arm["selection_use"] = bool(arm.get("selection_use") or rec.get("selection_use"))
    if adopt_fps:
        entry["baseline"] = entry.get("baseline") or adopt_fps[0]
    if len(adopt_fps) > 1:
        entry["comparison"] = entry.get("comparison") or adopt_fps[1]
        entry["quota_used"] = True


def _batch_entry(data: dict[str, Any], batch: str) -> dict[str, Any]:
    """取出（必要时初始化）某批的账本条目，并把旧 schema 迁移进来。"""
    batches = data.setdefault("batches", {})
    entry = batches.setdefault(batch, {})
    if not isinstance(entry.get("arms"), dict):
        entry["arms"] = {}
    _migrate_legacy(entry)
    entry.setdefault("baseline", None)
    entry.setdefault("comparison", None)
    entry.setdefault("quota_used", False)
    return entry


# ──────────────────────────────────────────────
# 预注册
# ──────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _parse_dt(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in _PREREG_DT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def validate_prereg(
    batch: str,
    fingerprint: str,
    *,
    baseline: Optional[str] = None,
    prereg_file: Optional[str | Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """校验"配额内那次对照"的预注册文件。

    返回 ``{"ok", "path", "sha256", "frozen_at", "reason"}``。
    ``ok=False`` 时调用方必须**拒绝**该 comparison 臂。
    """
    path = Path(prereg_file) if prereg_file else prereg_path(batch, fingerprint)
    result: dict[str, Any] = {
        "ok": False,
        "path": str(path),
        "sha256": None,
        "frozen_at": None,
        "reason": "",
    }
    if not path.is_file():
        result["reason"] = (
            f"未找到预注册文件：{path}\n"
            "  comparison 臂必须先写预注册（预测方向/采纳判据/负结果处置/写就时间），"
            "再用 `--prereg <file>` 或默认路径重跑。"
        )
        return result

    raw = path.read_bytes()
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 任何解析失败都算不合规
        result["reason"] = f"预注册文件不是合法 JSON：{exc}"
        return result
    if not isinstance(payload, dict):
        result["reason"] = "预注册文件顶层必须是 JSON 对象"
        return result

    problems: list[str] = []

    declared = str(payload.get("batch") or "").strip()
    if not declared:
        problems.append("缺少 `batch`（不写就可能是把别的批的预注册拿来用）")
    elif declared != batch:
        problems.append(f"`batch` 不匹配：文件写的是 {declared!r}，本次是 {batch!r}")

    variant = str(payload.get("variant_sha16") or "").strip()
    if not variant:
        problems.append("缺少 `variant_sha16`（预注册必须绑定到本次要跑的那个指纹）")
    elif variant != fingerprint:
        problems.append(
            f"`variant_sha16` 不匹配：文件写的是 {variant!r}，本次指纹是 {fingerprint!r}"
        )

    declared_base = str(payload.get("baseline_sha16") or "").strip()
    if not declared_base:
        problems.append("缺少 `baseline_sha16`")
    elif baseline and declared_base != baseline:
        problems.append(
            f"`baseline_sha16` 不匹配：文件写的是 {declared_base!r}，账本记录的基线是 {baseline!r}"
        )

    for field in _PREREG_TEXT_FIELDS:
        if not str(payload.get(field) or "").strip():
            problems.append(f"缺少 `{field}`")

    rule = payload.get("decision_rule")
    if not isinstance(rule, dict) or not str(rule.get("primary") or "").strip():
        problems.append("`decision_rule.primary`（采纳判据）缺失或为空")

    frozen = _parse_dt(payload.get("frozen_at"))
    if frozen is None:
        problems.append("`frozen_at`（写就时间）缺失或无法解析")
    else:
        result["frozen_at"] = payload.get("frozen_at")
        reference = now or datetime.now()
        if frozen.tzinfo is not None and reference.tzinfo is None:
            reference = reference.astimezone()
        elif frozen.tzinfo is None and reference.tzinfo is not None:
            frozen = frozen.replace(tzinfo=reference.tzinfo)
        if frozen > reference:
            problems.append(
                f"`frozen_at` 在未来（{payload.get('frozen_at')}）—— 预注册不允许在运行之后补写"
            )

    if problems:
        result["reason"] = "预注册不合规：\n  - " + "\n  - ".join(problems)
        return result

    result["ok"] = True
    result["reason"] = (
        f"预注册合规（frozen_at={result['frozen_at']}，sha256[:16]={result['sha256'][:16]}）"
    )
    return result


def _reverify_prereg(
    batch: str,
    fingerprint: str,
    baseline: Optional[str],
    rec: dict[str, Any],
    prereg_file: Optional[str | Path],
    now: Optional[datetime],
) -> dict[str, Any]:
    """comparison 臂复现时，核对预注册是否还是当初冻结的那一份。"""
    recorded = rec.get("prereg") or {}
    if not recorded.get("sha256"):
        # 迁移进来的历史数据没有记录 sha256：不阻断复现，但没有"未被改动"的保证。
        return {"ok": True, "sha256": None, "reason": "该臂未记录预注册 sha256（历史数据），不校验改动"}
    check = validate_prereg(
        batch,
        fingerprint,
        baseline=baseline,
        prereg_file=prereg_file or recorded.get("path"),
        now=now,
    )
    if not check["ok"]:
        check["reason"] = (
            "comparison 臂的预注册文件已不可用 —— 拒绝复现"
            "（预注册必须在运行前冻结，且之后不得移动/删除/修改）。\n  " + check["reason"]
        )
        return check
    if check["sha256"] != recorded["sha256"]:
        check["ok"] = False
        check["reason"] = (
            "comparison 臂的预注册文件**已被改动** → 拒绝："
            f"账本记录 sha256={recorded['sha256'][:16]}，当前={check['sha256'][:16]}。"
            "预注册一旦冻结就不得修改（要改就等于换一次实验）。"
        )
    return check


# ──────────────────────────────────────────────
# 判定与记账
# ──────────────────────────────────────────────


def _decision(
    allowed: bool,
    role: Optional[str],
    *,
    selection: bool,
    reason: str,
    prereg: Optional[dict[str, Any]],
    consumes_quota: bool,
    quota_used_before: bool,
    prior: list[str],
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "selection": selection,
        "role": role,
        "consumes_quota": consumes_quota,
        "quota_used_before": quota_used_before,
        "prereg": prereg,
        "reason": reason,
        "prior": prior,
    }


def evaluate(
    batch: str,
    fingerprint: str,
    *,
    purpose: str = "adopt",
    allow_selection: bool = False,
    prereg_file: Optional[str | Path] = None,
    ledger: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """**纯判定**（不写账本）：是否允许在该 batch 上运行这个口径指纹。"""
    data = ledger if ledger is not None else load_ledger()
    entry = _batch_entry(data, batch)
    arms: dict[str, Any] = entry["arms"]
    baseline: Optional[str] = entry.get("baseline")
    quota_used = bool(entry.get("quota_used"))
    purpose = (purpose or "adopt").strip().lower()
    prior = sorted(arms)
    rec = arms.get(fingerprint) or {}
    roles = set(rec.get("roles") or [])

    def decide(allowed, role, *, selection=False, reason, prereg=None, consumes_quota=False):
        return _decision(
            allowed,
            role,
            selection=selection,
            reason=reason,
            prereg=prereg,
            consumes_quota=consumes_quota,
            quota_used_before=quota_used,
            prior=prior,
        )

    # ① 同一臂复现（基线重复 / 对照臂重复）：不是新变体，不消耗配额。
    if roles & set(_ADOPT_ROLES):
        role = ROLE_BASELINE if ROLE_BASELINE in roles else ROLE_COMPARISON
        if role == ROLE_COMPARISON:
            check = _reverify_prereg(batch, fingerprint, baseline, rec, prereg_file, now)
            if not check["ok"]:
                return decide(False, role, reason=check["reason"])
        return decide(
            True,
            role,
            reason="同指纹重复运行（对照 / 复现 / 抖动测量），不是新变体；不消耗配额",
        )

    # ② 故意造坏的对照：验证"指标能不能检出"，不构成"选择口径"。
    if purpose == ROLE_PROBE:
        return decide(
            True,
            ROLE_PROBE,
            reason="用途=probe（故意造坏的对照，用于验证指标灵敏度），不构成『选择口径』；不消耗配额",
        )

    # ③ 此前已被标记为选择产物的指纹：重复运行仍然不得用于采纳。
    if ROLE_SELECTION in roles:
        return decide(
            True,
            ROLE_SELECTION,
            selection=True,
            reason="该指纹此前已被标记为 selection_use，重复运行仍然**不得用于采纳**；不消耗配额",
        )

    # ④ 该批尚无基线 → 第一个 adopt 指纹就是基线。
    if not baseline:
        return decide(
            True,
            ROLE_BASELINE,
            reason="该批尚无基线 → 本次记为 baseline，允许；不消耗配额（基线可重复跑）",
        )

    # ⑤ 配额内那一次对照：**必须先有合规预注册**。
    if not quota_used:
        check = validate_prereg(
            batch, fingerprint, baseline=baseline, prereg_file=prereg_file, now=now
        )
        if check["ok"]:
            return decide(
                True,
                ROLE_COMPARISON,
                prereg=check,
                consumes_quota=True,
                reason=f"配额内的一次 adopt 级对照 → 记为 comparison 臂；{check['reason']}",
            )
        if allow_selection:
            return decide(
                True,
                ROLE_SELECTION,
                selection=True,
                reason=(
                    "预注册不合规，但 JUDGE_ALLOW_SELECTION=1 显式放行 → 本次读数标记 "
                    "selection_use=true，**不得用于采纳**；不消耗配额。\n  " + check["reason"]
                ),
            )
        return decide(
            False,
            None,
            reason=(
                "同一批上的第二个 adopt 指纹（= 配额内那次对照）**必须先写预注册**。\n  "
                + check["reason"].replace("\n", "\n  ")
                + "\n  出路：① 写好预注册后重跑（默认路径或 --prereg）；"
                "② 换新样本；③ 若只是故意造坏的指标验证，设 JUDGE_VARIANT_PURPOSE=probe。"
            ),
        )

    # ⑥ 配额已用尽，又出现第三个不同 adopt 指纹。
    if allow_selection:
        return decide(
            True,
            ROLE_SELECTION,
            selection=True,
            reason=(
                "JUDGE_ALLOW_SELECTION=1：本批的 adopt 配额（基线 + 一次对照）已用尽，"
                "本次读数标记 selection_use=true，**不得用于采纳**；不消耗配额"
            ),
        )
    return decide(
        False,
        None,
        reason=(
            f"本批的 adopt 配额已用尽：基线 `{baseline}` + 对照臂 `{entry.get('comparison')}` "
            "已占满『基线 + 一次对照』。\n"
            "  规则：同一 batch 不得第二次用于选择口径（EVAL_DESIGN §3.3）。\n"
            "  出路：① 换新样本（正解）；② 若确为故意造坏的指标验证，设 JUDGE_VARIANT_PURPOSE=probe；\n"
            "  ③ 若确实要承担后果，加 --allow-selection / JUDGE_ALLOW_SELECTION=1"
            "（该次读数会被标记为选择产物，不得用于采纳）。"
        ),
    )


def record(
    batch: str,
    fingerprint: str,
    *,
    role: str = ROLE_BASELINE,
    purpose: str = "adopt",
    selection: bool = False,
    prereg: Optional[dict[str, Any]] = None,
    stamp: Optional[str] = None,
) -> dict[str, Any]:
    """把本次运行写入账本（幂等：同指纹只累加计数；角色/配额只升不降）。"""
    ledger = load_ledger()
    entry = _batch_entry(ledger, batch)
    arms: dict[str, Any] = entry["arms"]
    today = stamp or datetime.now().strftime("%Y-%m-%d")
    arm = arms.setdefault(fingerprint, _new_arm(today))
    if role and role not in arm["roles"]:
        arm["roles"].append(role)
    arm["runs"] = int(arm.get("runs") or 0) + 1
    arm["last_seen"] = today
    if purpose and purpose not in arm["purposes"]:
        arm["purposes"].append(purpose)
    arm["selection_use"] = bool(arm.get("selection_use") or selection or role == ROLE_SELECTION)

    if role == ROLE_BASELINE and not entry.get("baseline"):
        entry["baseline"] = fingerprint
    if role == ROLE_COMPARISON:
        entry["comparison"] = fingerprint
        entry["quota_used"] = True
        if prereg:
            arm["prereg"] = {
                "path": prereg.get("path"),
                "sha256": prereg.get("sha256"),
                "frozen_at": prereg.get("frozen_at"),
            }
    entry["arms"] = arms
    save_ledger(ledger)
    return arm


def check_and_record(
    batch: str,
    fingerprint: str,
    *,
    purpose: str = "adopt",
    allow_selection: bool = False,
    prereg_file: Optional[str | Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """判定 + （允许时）记账。返回判定结果，含 ``allowed`` / ``selection`` / ``role`` / ``reason``。"""
    decision = evaluate(
        batch,
        fingerprint,
        purpose=purpose,
        allow_selection=allow_selection,
        prereg_file=prereg_file,
        now=now,
    )
    if decision["allowed"]:
        decision["record"] = record(
            batch,
            fingerprint,
            role=decision.get("role") or ROLE_BASELINE,
            purpose=purpose,
            selection=bool(decision.get("selection")),
            prereg=decision.get("prereg"),
        )
    return decision
