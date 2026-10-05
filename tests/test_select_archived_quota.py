"""`scripts/select_archived_quota.py` 的回归测试（P4-3）。

只测**纯函数**：轴归类、池分布、按配额选。读真实轨迹池的部分不在这里测——
那个池在本机应用数据目录下、不属于仓库，测试不该依赖它存在。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "select_archived_quota.py"


def _load():
    spec = importlib.util.spec_from_file_location("select_archived_quota", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAQ = _load()


def _record(name: str, query: str = "q", tools=("web_search",), month: str = "2026-09") -> dict:
    return {
        "path": Path(f"traj_{name}.json"),
        "traj": {
            "query": query,
            "model": "m",
            "timestamp": f"{month}-01T00:00:00",
            "steps": [{"action": {"name": t}} for t in tools],
        },
    }


# ── 轴归类：只认**可观测属性** ──────────────────────────────────────────────


def test_language_bucket_splits_cjk_mixed_latin_and_empty():
    assert SAQ.language_bucket("\u4e2d\u6587\u95ee\u9898") == "cjk"
    assert SAQ.language_bucket("hello world") == "latin"
    assert SAQ.language_bucket("hello \u4e2d") == "mixed"
    assert SAQ.language_bucket("") == "empty"
    assert SAQ.language_bucket("   ") == "empty"


def test_stratum_of_backend_joins_tool_names_or_none():
    assert SAQ.stratum_of(_record("a", tools=("web_search",))["traj"], "backend") == "web_search"
    assert SAQ.stratum_of(_record("b", tools=("web_search", "search_docs"))["traj"], "backend") == "web_search+search_docs"
    assert SAQ.stratum_of(_record("c", tools=())["traj"], "backend") == "none"


def test_stratum_of_search_steps_only_counts_search_tools():
    """`search_docs` 与 `web_search` 都算检索工具；别的工具不算。"""
    assert SAQ.stratum_of(_record("a", tools=("web_search",))["traj"], "search_steps") == "with_search"
    assert SAQ.stratum_of(_record("b", tools=("search_docs",))["traj"], "search_steps") == "with_search"
    assert SAQ.stratum_of(_record("c", tools=("calculator",))["traj"], "search_steps") == "without_search"
    assert SAQ.stratum_of(_record("d", tools=())["traj"], "search_steps") == "without_search"


def test_stratum_of_month_model_and_unknown_axis():
    assert SAQ.stratum_of(_record("a", month="2026-08")["traj"], "month") == "2026-08"
    assert SAQ.stratum_of(_record("a")["traj"], "model") == "m"

    try:
        SAQ.stratum_of(_record("a")["traj"], "nope")
    except ValueError as exc:
        assert "未知配额轴" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("未知轴必须报错，不能静默给一个层名")


def test_step_tool_names_dedups_and_keeps_order():
    traj = {"steps": [{"action": {"name": "b"}}, {"action": {"name": "a"}}, {"action": {"name": "b"}}]}
    assert SAQ.step_tool_names(traj) == ["b", "a"]


# ── 池分布：报告模式与配额目标共用 ──────────────────────────────────────────


def test_pool_profile_reports_every_axis_with_shares():
    records = [
        _record("a", tools=("web_search",), month="2026-08"),
        _record("b", tools=("web_search",), month="2026-09"),
        _record("c", tools=("search_docs",), month="2026-09"),
    ]

    profile = SAQ.pool_profile(records)

    assert profile["n_trajectories"] == 3
    assert profile["oldest"].startswith("2026-08") and profile["newest"].startswith("2026-09")
    assert set(profile["by_key"]) == set(SAQ.QUOTA_KEYS)
    backend = profile["by_key"]["backend"]
    assert backend["counts"] == {"web_search": 2, "search_docs": 1}
    assert backend["share"]["web_search"] == round(2 / 3, 4)
    assert profile["by_key"]["search_steps"]["counts"] == {"with_search": 3}


# ── 配额选择 ────────────────────────────────────────────────────────────────


def _pool(a_count: int, b_count: int) -> list[dict]:
    return [_record(f"a{i}") for i in range(a_count)] + [
        _record(f"b{i}", tools=("search_docs",)) for i in range(b_count)
    ]


def test_proportional_target_follows_the_real_share():
    """按真实占比定目标 —— 这是「代表真实流量」的含义。"""
    result = SAQ.select_by_quota(_pool(8, 2), key="backend", limit=100, seed=1)

    assert result["target"] == {"search_docs": 20, "web_search": 80}
    assert result["achieved"] == {"search_docs": 2, "web_search": 8}, "池子不够就取满为止"
    assert result["representative"] is True
    assert result["zero_strata"] == []


def test_proportional_reports_strata_rounded_down_to_zero():
    """占比太小的层会被四舍五入成 0 —— **必须报出来**（空层不是"没差"）。"""
    result = SAQ.select_by_quota(_pool(99, 1), key="backend", limit=10, seed=1)

    assert result["target"]["search_docs"] == 0
    assert result["zero_strata"] == ["search_docs"]


def test_balanced_gives_every_stratum_at_least_one():
    """`balanced` 牺牲代表性，换"每层都别是空的"。"""
    result = SAQ.select_by_quota(_pool(99, 1), key="backend", limit=4, seed=1, mode="balanced")

    assert all(count >= 1 for count in result["achieved"].values()), result["achieved"]
    assert result["zero_strata"] == []
    assert result["representative"] is False, "balanced **不是**代表性抽样"


def test_selection_is_reproducible_by_seed():
    records = _pool(20, 20)

    first = SAQ.select_by_quota(records, key="backend", limit=10, seed=7)["chosen"]
    again = SAQ.select_by_quota(records, key="backend", limit=10, seed=7)["chosen"]

    assert first == again, "同种子必须完全一致"


def test_selection_shuffles_within_stratum_instead_of_taking_the_head():
    """层内是**打乱后取**，不是按文件顺序取头部（同 P0-3 的教训）。"""
    records = _pool(40, 0)

    picked = set()
    for seed in range(40):
        picked.update(SAQ.select_by_quota(records, key="backend", limit=3, seed=seed)["chosen"])

    assert len(picked) > 3, f"不同种子拿到了同一批：{sorted(picked)[:5]}（说明层内没有打乱）"


def test_selection_declares_its_limitations_and_note():
    """清单必须自带限定：可观测轴 ≠ 领域分布；balanced 不得报总体发生率。"""
    result = SAQ.select_by_quota(_pool(5, 5), key="backend", limit=4, seed=1)

    assert "领域分布" in result["limitations"]
    assert "放弃代表性" in result["note"]


# ── 读取与文件筛选 ──────────────────────────────────────────────────────────


def test_load_trajectory_skips_broken_and_non_object_files(tmp_path):
    bad = tmp_path / "traj_bad.json"
    bad.write_text("{不是 JSON", encoding="utf-8")
    array = tmp_path / "traj_array.json"
    array.write_text("[1, 2]", encoding="utf-8")
    good = tmp_path / "traj_good.json"
    good.write_text(json.dumps({"query": "q"}), encoding="utf-8")

    assert SAQ.load_trajectory(bad) is None
    assert SAQ.load_trajectory(array) is None
    assert SAQ.load_trajectory(good) == {"query": "q"}


def test_iter_trajectory_files_only_takes_traj_prefix(tmp_path):
    (tmp_path / "traj_a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "other.json").write_text("{}", encoding="utf-8")

    names = [path.name for path in SAQ.iter_trajectory_files(tmp_path)]

    assert names == ["traj_a.json"]


# ── 合格性过滤：**先拒绝，再抽样** ──────────────────────────────────────────


def test_apply_filters_drops_mock_by_default():
    """`mock` **不是真实流量**（实测池里 21 条）——按配额抽样若照搬分布会把它按比例采进来。"""
    records = [_record("a"), _record("b")]
    records[1]["traj"]["model"] = "mock"

    kept, dropped = SAQ.apply_filters(records)

    assert [r["traj"]["model"] for r in kept] == ["m"]
    assert dropped == {"excluded_model": 1}


def test_apply_filters_can_require_a_search_tool():
    """池里 20.6% 的轨迹**没有任何工具调用**——它们没有可判定的检索步。"""
    records = [_record("a", tools=("web_search",)), _record("b", tools=()), _record("c", tools=("calculator",))]

    kept, dropped = SAQ.apply_filters(records, require_search=True)

    assert [r["path"].name for r in kept] == ["traj_a.json"]
    assert dropped == {"no_search_tool": 2}


def test_apply_filters_reports_what_it_dropped_even_when_nothing_is_dropped():
    kept, dropped = SAQ.apply_filters([_record("a")])

    assert len(kept) == 1
    assert dropped == {}, "没挡掉也要返回空计数（调用方据此判断要不要打印）"
