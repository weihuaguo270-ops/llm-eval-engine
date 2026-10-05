"""采集脚本 P0 修复的回归测试（可复现抽样 / 零样本门禁 / meta 计数完整 / 快照 sha 自洽）。

被测文件是**归档**的 `reports/_revoked_20261003/code/scripts/collect_live_snapshot.py`。

为什么**不能** import 它：第 48 行 `from eval_engine.core.search_step import (...)`，
而 `search_step.py` 已被 `git rm`、**磁盘上不存在**（只在 git 历史里）。
故这里用 **ast 按名取出单个函数、单独编译执行**——对"归档且不可导入"的代码，
这是唯一能**真跑行为**（而非只查结构）的办法。代价必须写明：

- 取出的函数必须**自包含**（只依赖注入进命名空间的名字）。注意原模块有
  `from __future__ import annotations`，单独编译时**没有**它，所以注解会被立即求值 →
  必须把 `Any` 之类注入进去。
- `cmd_collect` 这类会 spawn agent 的函数**无法这样测**，只能查结构（ast）。

P0 四项：① meta 计数不得硬编码键 ② 零样本请求/层清空必须能失败 ③ 层内带种子打乱
④ 快照 sha 必须与磁盘文件一致。另含 **P1-3**：快照寿期声明（`snapshot_policy`）。

> 文件名里的 "p0" 是历史遗留（先做 P0 后加 P1-3）；两者都是**采集器的守卫**，故留在一起。
> ⚠️ 被测文件在 `reports/` 内，而 `reports/` 被 `.gitignore` 忽略 →
> **clone 出来的仓库没有归档副本，整套守卫会跳过**（而不是报 FileNotFoundError）。
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import time
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
ARCHIVED = (
    REPO / "reports" / "_revoked_20261003" / "code" / "scripts" / "collect_live_snapshot.py"
)

if not ARCHIVED.exists():
    # 归档副本在 `reports/` 内，而 `reports/` 被 `.gitignore` 忽略 → **clone 出来的仓库没有它**。
    # 此时整套守卫跳过，而不是让测试报 FileNotFoundError。**跳过是有代价的**：
    # 没有归档副本时这些守卫不生效（已写进文件头 docstring）。
    pytest.skip(
        "归档副本不在（reports/ 在 .gitignore 内）：采集器守卫只在持有归档副本时生效",
        allow_module_level=True,
    )


def _tree() -> ast.Module:
    return ast.parse(ARCHIVED.read_text(encoding="utf-8"))


def _literal(name: str):
    """取模块级常量字面量（``AnnAssign`` 与 ``Assign`` 都认）。"""
    for node in _tree().body:
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(value)
    raise AssertionError(f"源码里找不到模块级常量 {name}")


def _module_constants() -> dict:
    """抽出归档文件里**所有模块级字面量常量**，供逐函数编译时自动注入。

    为什么必须自动：`_function` 单独编译一个函数时，要把它依赖的模块级名字补进命名空间，
    **漏一个就 `NameError`**。P1-3 先后给 `_notarize` 加了 `COLUMN` 与
    `SNAPSHOT_REVIEW_DAYS`，手动清单**连挂两轮** —— 手动维护本身就是错的改法。
    非字面量（正则编译、函数调用等）抽不出来，仍需在该函数的 `namespace` 里显式给。
    """
    out: dict = {}
    for node in _tree().body:
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if isinstance(target, ast.Name):
            try:
                out[target.id] = ast.literal_eval(value)
            except (ValueError, TypeError):
                continue
    return out


def _function_node(name: str) -> ast.FunctionDef:
    """取出某个顶层函数的 **ast 节点**（供结构检查用）。"""
    for node in _tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"源码里找不到函数 {name}")


def _function(name: str, namespace: Optional[dict] = None, _resolving: tuple = ()):
    """把某个顶层函数**单独编译**出来（模块整体不可导入，只能逐函数取）。

    命名空间 = `Any`/`Optional` + **自动注入的模块级字面量常量**
    + **自动注入它引用到的其它顶层函数**（递归）+ 调用方显式补的非字面量依赖（模块等）。

    两步自动注入都是被"漏注入 → NameError"逼出来的：P1-3 给 `_notarize` 先后加了
    `COLUMN`（常量）、`SNAPSHOT_REVIEW_DAYS`（常量）、`_review_by`（函数）——
    手动清单**连挂三轮**。教训：**修实例不修类**，就会一轮一轮地挂。
    """
    node = _function_node(name)
    module = ast.Module(body=[node], type_ignores=[])
    scope: dict = {"Any": Any, "Optional": Optional}
    scope.update(_module_constants())

    referenced = {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }
    for other in _tree().body:
        if (
            isinstance(other, ast.FunctionDef)
            and other.name in referenced
            and other.name != name
            and other.name not in _resolving
        ):
            scope[other.name] = _function(other.name, namespace, _resolving + (name,))

    scope.update(namespace or {})
    exec(compile(ast.fix_missing_locations(module), "<archived>", "exec"), scope)  # noqa: S102
    return scope[name]


def _meta_dict() -> ast.Dict:
    for node in ast.walk(_tree()):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Dict)
            and any(isinstance(t, ast.Name) and t.id == "meta" for t in node.targets)
        ):
            return node.value
    raise AssertionError("找不到 `meta = {...}` 字面量")


def _meta_value(key: str) -> ast.AST:
    literal = _meta_dict()
    for k, v in zip(literal.keys, literal.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    raise AssertionError(f"meta 里没有键 {key}")


# ── P0-1：meta 计数不得硬编码键 ─────────────────────────────────────────────


def test_count_values_counts_every_real_value_and_never_drops_a_row():
    """按**真实取值**计数。旧版硬编码 ("success","failure")，把另外两类静默丢掉。"""
    count = _function("_count_values")
    rows = [{"s": "success"}] * 51 + [{"s": "tool_error"}] * 25 + [{"s": "no_content"}] * 4

    counts = count(rows, "s")

    assert counts == {"success": 51, "tool_error": 25, "no_content": 4}
    assert sum(counts.values()) == len(rows), "一行都不许丢"
    assert list(counts) == ["success", "tool_error", "no_content"], "按次数降序"
    assert count([], "s") == {}


def test_batch_meta_computes_outcome_strata_from_real_values():
    """meta 的 outcome_strata 必须是 `_count_values` 的**调用**，不是写死键的推导式。"""
    node = _meta_value("outcome_strata")
    assert isinstance(node, ast.Call), "outcome_strata 必须由函数计算"
    assert getattr(node.func, "id", None) == "_count_values"


def test_batch_meta_records_seed_selection_and_coverage():
    """meta 必须留下采样种子、选中清单与自检结论——三者缺一，这批就**不可复核**。"""
    for key in ("sample_seed", "sampling", "outcome_strata"):
        _meta_value(key)
    sampling = _meta_value("sampling")
    assert isinstance(sampling, ast.Dict)
    fields = {k.value for k in sampling.keys if isinstance(k, ast.Constant)}
    assert {
        "limit", "chosen", "chosen_strata", "pool_strata", "leftover",
        "coverage_report", "coverage_ok",
    } <= fields, f"sampling 字段不全：{sorted(fields)}"


# ── P0-3：层内带种子打乱、且可复现 ──────────────────────────────────────────


def _choose():
    return _function(
        "_choose_requests",
        {"STRATUM_BY_STYLE": _literal("STRATUM_BY_STYLE"), "random": random},
    )


def test_choose_requests_is_reproducible_and_covers_every_stratum():
    """同池子 + 同 limit + 同种子 ⇒ 同一批请求；且每层都取到。"""
    choose = _choose()
    pool = _literal("CANDIDATE_REQUESTS")

    first = choose(list(pool), 16, 20261005)
    again = choose(list(pool), 16, 20261005)

    assert [r["id"] for r in first["chosen"]] == [r["id"] for r in again["chosen"]], (
        "同种子必须完全一致（可复现）"
    )
    assert first["starved_strata"] == [], "成功池 5 层、limit=16，应当全部取到"
    assert set(first["chosen_strata"]) == set(first["pool_strata"])


def test_choose_requests_shuffles_within_stratum_instead_of_taking_the_head():
    """层内是**打乱后取**，不是"按书写顺序取头部"。

    做法：`limit=1` 时轮转只会落在字母序第一层（`ambiguous`，池中恰有 w12–w14），
    用 200 个不同种子去取，应当出现**不止一个** id —— 旧实现永远只取书写位置最前的那条。
    """
    choose = _choose()
    pool = _literal("CANDIDATE_REQUESTS")

    picked = {choose(list(pool), 1, seed)["chosen"][0]["id"] for seed in range(200)}

    assert len(picked) > 1, f"不同种子拿到同一批：{picked}（说明层内没有打乱）"


def test_choose_requests_reports_strata_starved_by_a_small_limit():
    """`limit` < 层数时字母序靠后的层一条都取不到 —— 必须**显式报出**，不能悄悄少采。

    （旧实现同样少采，但没有 `starved_strata` 这个出口，于是"某层 0 样本"完全静默。）
    """
    choose = _choose()
    result = choose(list(_literal("CANDIDATE_REQUESTS")), 1, 7)

    assert result["chosen_strata"] == ["ambiguous"]
    assert "strong" in result["starved_strata"] and "weak" in result["starved_strata"]
    assert len(result["starved_strata"]) == len(result["pool_strata"]) - 1


# ── P0-2：覆盖率门禁 ────────────────────────────────────────────────────────


def test_coverage_gate_fails_on_emptied_stratum_and_zero_sample_requests():
    """把"整层静默消失"与"零样本请求"变成**会失败**（w12–w14 的实际情形）。"""
    gate = _function("_coverage_gate")
    selection = {
        "chosen": [{"id": "w12"}, {"id": "w13"}, {"id": "w14"}, {"id": "w01"}],
        "chosen_strata": ["ambiguous", "strong"],
        "pool_strata": ["ambiguous", "strong", "weak"],
        "starved_strata": ["weak"],
        "leftover": {},
        "seed": 1,
    }
    strata = {"w12": "ambiguous", "w13": "ambiguous", "w14": "ambiguous", "w01": "strong"}

    result = gate(selection, [{"case_id": "w01"}], strata, max_zero_sample_ratio=0.25)

    assert result["ok"] is False
    assert result["empty_strata"] == ["ambiguous", "weak"]
    assert result["zero_sample_requests"] == ["w12", "w13", "w14"]
    assert result["zero_sample_ratio"] == 0.75
    assert result["samples_by_stratum"] == {"strong": 1}
    assert len(result["problems"]) == 2, result["problems"]


def test_coverage_gate_passes_when_every_stratum_yields_samples():
    gate = _function("_coverage_gate")
    selection = {
        "chosen": [{"id": "w01"}, {"id": "w12"}],
        "chosen_strata": ["ambiguous", "strong"],
        "pool_strata": ["ambiguous", "strong"],
        "starved_strata": [],
        "leftover": {},
        "seed": 1,
    }
    strata = {"w01": "strong", "w12": "ambiguous"}

    result = gate(selection, [{"case_id": "w01"}, {"case_id": "w12"}], strata)

    assert result["ok"] is True
    assert result["problems"] == []
    assert result["zero_sample_ratio"] == 0.0


# ── P0-4：快照 sha 必须与磁盘文件一致 ───────────────────────────────────────


class _FrozenClock:
    """冻结"采集时刻"：**无参** `strftime` 返回固定时间；**带参**的（如 `_review_by` 里的
    日期格式化）转交真 `time`。

    取**正午**而不是零点——免得时区/夏令时把日期推掉一天，让"90 天"的断言变脆。
    """

    STAMP = "2026-10-05T12:00:00"

    def strftime(self, fmt, *args):
        return time.strftime(fmt, *args) if args else self.STAMP

    strptime = staticmethod(time.strptime)
    mktime = staticmethod(time.mktime)
    localtime = staticmethod(time.localtime)


def _notarize():
    """`_notarize` 依赖时间；这里用冻结时钟，让"同一秒撞击"可确定性复现。

    模块级常量（`BACKEND` / `STRATUM_BY_STYLE` / `COLUMN` / `SNAPSHOT_REVIEW_DAYS` …）
    由 `_function` **自动注入**；这里只需补它依赖的**非字面量**：模块与冻结时钟。
    """
    return _function(
        "_notarize",
        {
            "hashlib": hashlib,
            "json": json,
            "time": _FrozenClock(),
            "Path": Path,
        },
    )


_REQUEST = {"id": "w01", "query": "q", "style": "single_fact"}
_RUN = {"answer": "a", "trajectory": {"model": "m", "session_id": "s"}, "duration_s": 1.0}


def test_notarize_returns_a_sha_that_matches_the_file_on_disk(tmp_path):
    notarize = _notarize()

    first = notarize(tmp_path, _REQUEST, _RUN)
    assert first["sha256"] == hashlib.sha256(Path(first["path"]).read_bytes()).hexdigest()

    again = notarize(tmp_path, _REQUEST, _RUN)  # 同内容重放
    assert again["sha256"] == first["sha256"]


def test_notarize_refuses_to_return_a_sha_that_disagrees_with_the_file(tmp_path):
    """同一 snapshot_id 撞上**不同内容**时必须显式失败，绝不静默返回对不上的 sha。

    （旧版"已存在就不写、却仍返回本次算的 sha"。触发需同一请求同一秒重跑 ⇒ 实际不可达，
    但 sha 是**证据本体**，宁可失败。）
    """
    notarize = _notarize()
    first = notarize(tmp_path, _REQUEST, _RUN)

    with pytest.raises(RuntimeError) as exc:
        notarize(tmp_path, _REQUEST, dict(_RUN, answer="DIFFERENT"))

    assert "sha256" in str(exc.value)
    # 既有文件绝不被覆盖
    assert hashlib.sha256(Path(first["path"]).read_bytes()).hexdigest() == first["sha256"]


# ── P1-3：快照寿期声明 ──────────────────────────────────────────────────────


def test_notarize_emits_snapshot_policy_with_review_by(tmp_path):
    """快照返回值必须带寿期声明，且 `review_by` 恰好是采集时刻 + 90 天。

    日期差用 `datetime` **独立算**（不重复实现里的 mktime/86400 公式），才算真检查。
    """
    notarize = _notarize()

    policy = notarize(tmp_path, _REQUEST, _RUN)["snapshot_policy"]

    assert policy["recollectable"] is False
    assert policy["review_interval_days"] == _literal("SNAPSHOT_REVIEW_DAYS")
    assert policy["evidence_kind"] == _literal("COLUMN")
    assert (date.fromisoformat(policy["review_by"]) - date(2026, 10, 5)).days == 90


def test_snapshot_policy_is_outside_the_hashed_payload():
    """P1-3 的关键决定：**策略不进哈希**。

    若把 `snapshot_policy` 塞进 `payload`，同一份证据就会因为**策略不同**而得到不同的 sha
    —— 那是错的。故这里查结构：`payload`（含 `trajectory`）里没有它，返回值（含
    `snapshot_id`）里有它。
    """
    node = _function_node("_notarize")
    dicts = [item for item in ast.walk(node) if isinstance(item, ast.Dict)]

    def keys_of(item: ast.Dict) -> set:
        return {key.value for key in item.keys if isinstance(key, ast.Constant)}

    payload = next(item for item in dicts if "trajectory" in keys_of(item))
    returned = next(item for item in dicts if "snapshot_id" in keys_of(item))

    assert "snapshot_policy" not in keys_of(payload), "策略不得进被哈希的 payload"
    assert "snapshot_policy" in keys_of(returned), "策略必须随返回值进 manifest"


def test_module_constants_are_auto_injected():
    """锁住"自动注入常量"这个机制本身——它是为了终结"漏注入 → NameError"的反复失败。"""
    constants = _module_constants()
    assert constants["COLUMN"] == "live_snapshot"
    assert constants["SNAPSHOT_REVIEW_DAYS"] == 90
    assert constants["SAMPLE_SEED"] == 20261005
    assert constants["BACKEND"], "非空即可（值随后端变化）"


def test_referenced_top_level_functions_are_auto_injected():
    """被引用到的顶层函数也要自动注入：`_notarize` 现在会调用 `_review_by`。

    顺带独立验一遍 90 天的算法（用注入进去的那个函数直接算）。
    """
    notarize = _notarize()
    review_by = notarize.__globals__["_review_by"]

    assert review_by("2026-10-05T12:00:00") == "2027-01-03", "90 天后应是 2027-01-03"
    assert review_by("解析不了的时间串") == "", "解析失败必须返回空串——不猜"


# ── P2-1：拒绝留档 ──────────────────────────────────────────────────────────


def test_rejection_ledger_records_what_it_can_and_declares_its_blind_spots():
    """只记**本阶段能确定**的类别，并把**看不见的类别也列出来**。

    `w12–w14` 的教训：**「某层为什么是空的」不该靠事后推断。**
    而「看不见的那些」同样要留档——否则读的人会以为这就是全部。
    """
    ledger = _function("_rejection_ledger")
    selection = {
        "chosen": [{"id": "w01"}, {"id": "w12"}, {"id": "w13"}],
        "leftover": {"weak": ["w08", "w09"], "long_tail": []},
        "chosen_strata": ["ambiguous", "strong"],
        "pool_strata": ["ambiguous", "long_tail", "partial", "strong", "weak"],
        "starved_strata": [],
        "seed": 1,
    }

    result = ledger(selection, selection["chosen"], [{"case_id": "w01"}])

    counts = result["counts_by_category"]
    assert counts == {"limit_not_selected": 2, "no_search_step": 2}
    assert set(counts) <= set(result["categories"]), "不得出现受控词表以外的类别"
    assert len(result["not_visible_here"]) == 5, "看不见的类别也必须留档"
    assert result["entries"], "有拒绝就该有条目"
    assert all(
        {"id", "stage", "category", "reason"} <= set(entry) for entry in result["entries"]
    ), "每条拒绝都要有 id / 阶段 / 类别 / 原因"


def test_rejection_ledger_is_empty_but_still_declares_blind_spots():
    """没有拒绝也要出文件——**空和有是两种状态**，不能靠「文件不在」来推断。"""
    ledger = _function("_rejection_ledger")
    selection = {
        "chosen": [{"id": "w01"}],
        "leftover": {},
        "chosen_strata": ["strong"],
        "pool_strata": ["strong"],
        "starved_strata": [],
        "seed": 1,
    }

    result = ledger(selection, selection["chosen"], [{"case_id": "w01"}])

    assert result["entries"] == []
    assert result["counts_by_category"] == {}
    assert len(result["not_visible_here"]) == 5


# ── P3-2：归档流水线**不可导入**（把外部约束写成**可执行断言**） ────────────


def test_archived_pipeline_stays_unimportable_until_search_step_returns():
    """归档采集器依赖 `eval_engine.core.search_step`，而它已被 `git rm`。

    **这条断言的用处是反向的**：它现在必须通过；一旦有人把 `search_step.py` 恢复回来，
    它就会挂 —— 那就该回去更新 P0/P1 那几份留档里「无法端到端验证」的限定，
    并真正跑一次采集器，验证那几处改动（当时只能靠「逐函数编译 + 单测」验证行为）。
    """
    repo_core = REPO / "src" / "eval_engine" / "core"
    archived_core = ARCHIVED.parents[1] / "src" / "eval_engine" / "core"

    assert not (repo_core / "search_step.py").exists(), (
        "`search_step.py` 回来了 → 归档流水线可能已可导入；"
        "请更新 P0/P1 留档里「无法端到端验证」的限定，并重跑采集器"
    )
    assert not (archived_core / "search_step.py").exists()

    with pytest.raises(ImportError):
        import eval_engine.core.search_step  # noqa: F401


# ── CLI：新增开关必须存在 ───────────────────────────────────────────────────


def test_cli_exposes_sample_seed_and_gate_threshold():
    calls = [
        node
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument"
    ]
    flags = {
        node.args[0].value
        for node in calls
        if node.args and isinstance(node.args[0], ast.Constant)
    }
    assert "--sample-seed" in flags
    assert "--max-zero-sample-ratio" in flags
