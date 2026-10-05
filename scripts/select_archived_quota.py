#!/usr/bin/env python
"""select_archived_quota — 对**归档真实轨迹池**做「先量分布、再按配额选」。

为什么需要它（P4-3）
--------------------
归档真实轨迹是**真实流量**（不可由人凭空设计），本仓此前只是"顺手采到多少算多少"。
对标 DeepResearch Bench 的做法：**先量出真实分布，再按分布配额取题**——
这样批次的构成是**刻意选定的、可报的**，而不是碰巧的。

零 API
------
只读本机轨迹文件，**不重跑 agent、不联网、不改动池子里的任何文件**。
默认池位置：``%LOCALAPPDATA%\\react-agent\\trajectories``（实测 791 个文件 / 3.75 MB /
跨度 2026-08-18 → 2026-10-03）。

两种模式
--------
- **不传 `--limit` ⇒ 只报分布**：把池子按可观测属性统计出来。**这就是配额目标本身。**
- 传 `--limit N` ⇒ 按配额选，并把 ``selection_manifest.json`` 落盘（**必须给 `--out`**）。

⚠️ **代表性 vs 富集，必须显式区分**（本项目的既定纪律）：
``--mode proportional`` 按真实分布取 ⇒ **代表真实流量**；
``--mode balanced`` 每层先保一条 ⇒ 为"每层都要可判"而**放弃代表性**。
后者**不得据此报总体发生率**；清单里会写明用的是哪一种。

⚠️ 可观测属性**不等于"领域分布"**：真正的域配额需要给请求打领域标签（本工具不打）。
它是**在无标签前提下的下界做法**，这一点写进清单的 ``limitations``。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

#: 认定"这是检索工具"的本地名单。**刻意不从已撤销的 `search_step.is_search_tool` 导入**
#: （那个模块已被 `git rm`，这里不制造新的死依赖）。与那条线的名单可能有差异——
#: 公网分栏的采集器另有自己的步级后端闸门（`--require-tool web_search`）。
SEARCH_TOOL_NAMES = ("web_search", "search_docs")

#: 可用的配额轴
QUOTA_KEYS = ("backend", "language", "search_steps", "month", "model")

DEFAULT_SEED = 20261005

_CJK = re.compile(r"[\u4e00-\u9fff]")


def default_pool() -> Path:
    """默认轨迹池：`%LOCALAPPDATA%\\react-agent\\trajectories`。"""
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or ""
    return Path(local) / "react-agent" / "trajectories" if local else Path("react-agent/trajectories")


def iter_trajectory_files(pool: Path) -> list[Path]:
    return sorted(pool.glob("traj_*.json"))


def load_trajectory(path: Path) -> Optional[dict[str, Any]]:
    """读一条轨迹；读不动/不是对象 → `None`（**跳过而不是炸**，池子里可能有半截文件）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def step_tool_names(trajectory: dict[str, Any]) -> list[str]:
    """一条轨迹里出现过的工具名（去重、保持稳定顺序）。"""
    names: list[str] = []
    for step in trajectory.get("steps") or []:
        action = step.get("action") or {}
        name = action.get("name")
        if name and name not in names:
            names.append(str(name))
    return names


def language_bucket(text: str) -> str:
    """粗分语种：CJK 字符占比 ≥ 0.3 → `cjk`；> 0 → `mixed`；否则 `latin`。"""
    stripped = re.sub(r"\s+", "", text or "")
    if not stripped:
        return "empty"
    ratio = len(_CJK.findall(stripped)) / len(stripped)
    if ratio >= 0.3:
        return "cjk"
    return "mixed" if ratio > 0 else "latin"


def stratum_of(trajectory: dict[str, Any], key: str) -> str:
    """按配额轴取该轨迹的层名（层名必须是**可观测属性**，不能靠推断语义）。"""
    if key == "backend":
        names = step_tool_names(trajectory)
        return "+".join(names) if names else "none"
    if key == "language":
        return language_bucket(str(trajectory.get("query") or ""))
    if key == "search_steps":
        tools = step_tool_names(trajectory)
        return "with_search" if any(t in SEARCH_TOOL_NAMES for t in tools) else "without_search"
    if key == "month":
        return str(trajectory.get("timestamp") or "unknown")[:7]
    if key == "model":
        return str(trajectory.get("model") or "unknown")
    raise ValueError(f"未知配额轴：{key}（可用：{QUOTA_KEYS}）")


def _count(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def pool_profile(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """把池子按**每个**配额轴统计一遍——报告模式与配额目标都用它。"""
    by_key: dict[str, Any] = {}
    for key in QUOTA_KEYS:
        counts = _count([stratum_of(record["traj"], key) for record in records])
        total = sum(counts.values())
        by_key[key] = {
            "counts": counts,
            "share": {name: round(n / total, 4) for name, n in counts.items()} if total else {},
        }
    stamps = sorted(str(r["traj"].get("timestamp") or "") for r in records)
    return {
        "n_trajectories": len(records),
        "oldest": stamps[0] if stamps else None,
        "newest": stamps[-1] if stamps else None,
        "by_key": by_key,
    }


def select_by_quota(
    records: Sequence[dict[str, Any]],
    *,
    key: str = "backend",
    limit: int,
    seed: int = DEFAULT_SEED,
    mode: str = "proportional",
) -> dict[str, Any]:
    """按配额选，并**把目标与实际都写清楚**（P4-3）。

    - ``proportional``：每层配额 = `round(limit × 该层真实占比)` ⇒ **代表真实流量**；
    - ``balanced``：先每层保一条、再轮转补齐 ⇒ 为"每层都要可判"而**放弃代表性**。

    层内用**带种子打乱**后取（同 P0-3 的教训：绝不按书写顺序取头部）。
    取到 0 条的层**必须报出来**——空层不是"没差"，是"这一层没有被测到"。
    """
    if mode not in ("proportional", "balanced"):
        raise ValueError(f"未知模式：{mode}（可用：proportional / balanced）")
    buckets: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        buckets.setdefault(stratum_of(record["traj"], key), []).append(record)
    rng = random.Random(seed)
    for rows in buckets.values():
        rng.shuffle(rows)
    total = len(records)

    target: dict[str, int] = {}
    if mode == "proportional":
        for name, rows in buckets.items():
            target[name] = int(round(limit * len(rows) / total)) if total else 0
    else:
        for name in buckets:
            target[name] = 1
        remaining = limit - sum(target.values())
        names = sorted(buckets)
        index = 0
        while remaining > 0 and names:
            name = names[index % len(names)]
            if target.get(name, 0) < len(buckets[name]):
                target[name] = target.get(name, 0) + 1
                remaining -= 1
            index += 1
            if index > limit * len(names) + len(names):  # 只会取到取不动为止
                break

    chosen: list[dict[str, Any]] = []
    achieved: dict[str, int] = {}
    for name in sorted(buckets):
        want = min(target.get(name, 0), len(buckets[name]))
        picked = buckets[name][:want]
        chosen.extend(picked)
        achieved[name] = len(picked)
    zero_strata = sorted(name for name in buckets if achieved.get(name, 0) == 0)
    return {
        "quota_key": key,
        "mode": mode,
        "seed": seed,
        "limit": limit,
        "n_pool": total,
        "target": dict(sorted(target.items())),
        "achieved": dict(sorted(achieved.items())),
        "zero_strata": zero_strata,
        "representative": mode == "proportional",
        "chosen": [str(record["path"]) for record in chosen],
        "limitations": (
            "配额轴是**可观测属性**，不等于「领域分布」——真正的域配额需要给请求打领域标签"
            "（本工具不打）。故它是**无标签前提下的下界做法**。"
        ),
        "note": (
            "`proportional` 按真实占比取 ⇒ 代表真实流量；`balanced` 每层保底 ⇒ **放弃代表性**，"
            "不得据此报总体发生率。`zero_strata` 非空表示**有层没被测到**，必须随结论一起引用。"
        ),
    }


def apply_filters(
    records: Sequence[dict[str, Any]],
    *,
    exclude_models: Sequence[str] = ("mock",),
    require_search: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """采样前的**合格性过滤**：先拒绝，再抽样。

    实测（791 条池）暴露两个**必须挡掉**的东西——否则按配额抽样会把它们按比例采进来：

    - `model = mock`：**21 条**。mock 不是真实流量，混进"代表性抽样"是自欺；
    - **没有任何工具调用**：**163 条（20.6%）**。它们没有可判定的检索步。

    返回 ``(保留下来的, 被挡掉的原因计数)``——**挡掉什么也要留档**（同 P2-1 的纪律）。
    """
    blocked = set(exclude_models)
    kept: list[dict[str, Any]] = []
    dropped: dict[str, int] = {}
    for record in records:
        if str(record["traj"].get("model") or "") in blocked:
            dropped["excluded_model"] = dropped.get("excluded_model", 0) + 1
            continue
        if require_search and not any(
            name in SEARCH_TOOL_NAMES for name in step_tool_names(record["traj"])
        ):
            dropped["no_search_tool"] = dropped.get("no_search_tool", 0) + 1
            continue
        kept.append(record)
    return kept, dropped


def _print_profile(profile: dict[str, Any]) -> None:
    print(f"轨迹 {profile['n_trajectories']} 条｜跨度 {profile['oldest']} .. {profile['newest']}")
    for key, item in profile["by_key"].items():
        head = list(item["counts"].items())[:6]
        tail = "" if len(item["counts"]) <= 6 else f" …（共 {len(item['counts'])} 层）"
        shown = "｜".join(f"{name} {n}（{item['share'][name]:.1%}）" for name, n in head)
        print(f"  [{key}] {shown}{tail}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="归档真实轨迹：量分布 / 按配额选")
    parser.add_argument("--pool", type=Path, default=None, help="轨迹目录（默认 %%LOCALAPPDATA%%\\react-agent\\trajectories）")
    parser.add_argument("--quota-key", choices=QUOTA_KEYS, default="backend")
    parser.add_argument("--mode", choices=("proportional", "balanced"), default="proportional")
    parser.add_argument("--limit", type=int, default=None, help="不传 ⇒ 只报分布")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--exclude-batch", type=Path, default=None,
                        help="读该批次的 agent_runs.json，排除**自有采集**的 session（本仓既定纪律）")
    parser.add_argument("--exclude-model", default="mock",
                        help="按 model 名排除（逗号分隔）。默认排除 mock —— **mock 不是真实流量**，"
                             "照搬分布会把它按比例采进来")
    parser.add_argument("--require-search", action="store_true",
                        help="只保留**含检索工具调用**的轨迹（实测池里 20.6%% 的轨迹没有任何工具调用）")
    parser.add_argument("--out", type=Path, default=None, help="选择模式的清单落盘路径（选择模式必填）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    pool = args.pool or default_pool()
    if not pool.is_dir():
        print(f"池目录不存在：{pool}")
        return 2

    excluded: set[str] = set()
    if args.exclude_batch:
        runs = args.exclude_batch / "agent_runs.json"
        if runs.exists():
            try:
                payload = json.loads(runs.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = []
            for row in payload if isinstance(payload, list) else []:
                if isinstance(row, dict) and row.get("session_id"):
                    excluded.add(str(row["session_id"]))

    records: list[dict[str, Any]] = []
    skipped = 0
    for path in iter_trajectory_files(pool):
        traj = load_trajectory(path)
        if traj is None:
            skipped += 1
            continue
        if excluded and str(traj.get("session_id")) in excluded:
            skipped += 1
            continue
        records.append({"path": path, "traj": traj})

    print(f"池 = {pool}")
    print(f"读入 {len(records)} 条｜跳过 {skipped} 条（读不动或属自有采集）")
    exclude_models = tuple(m.strip() for m in str(args.exclude_model).split(",") if m.strip())
    records, dropped = apply_filters(
        records, exclude_models=exclude_models, require_search=args.require_search
    )
    if dropped:
        print(f"合格性过滤挡掉 {sum(dropped.values())} 条：{dropped}"
              "（**挡掉什么也要留档**——同 P2-1 的纪律）")
    profile = pool_profile(records)
    _print_profile(profile)

    if args.limit is None:
        print("\n（未传 --limit ⇒ 只报分布。上面的占比就是**配额目标**。）")
        return 0

    if not args.out:
        print("\n❌ 选择模式必须给 --out")
        return 2
    selection = select_by_quota(
        records, key=args.quota_key, limit=args.limit, seed=args.seed, mode=args.mode
    )
    selection["pool"] = str(pool)
    selection["profile"] = profile
    selection["dropped"] = dropped
    selection["filters"] = {
        "exclude_models": list(exclude_models),
        "require_search": bool(args.require_search),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 按 {args.quota_key} 配额选（{args.mode}，limit={args.limit}，seed={args.seed}）")
    for name in sorted(selection["achieved"]):
        print(f"  {name:28} 目标 {selection['target'].get(name, 0):3}｜实际 {selection['achieved'][name]:3}")
    if selection["zero_strata"]:
        print(f"  ⚠️ **取到 0 条的层**：{selection['zero_strata']}"
              "（该层没有被测到，必须随结论一起引用）")
    print(f"  代表性 = {selection['representative']}（{selection['mode']}）")
    print(f"  [written] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
