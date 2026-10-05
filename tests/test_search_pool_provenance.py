"""请求池的出处（provenance）必须有记录——**锁住"题目从哪来"这一环**。

为什么这个测试放在 `tests/`（而不是归档目录里）：
被测对象是 `reports/_revoked_20261003/code/scripts/collect_live_snapshot.py`。
那条线虽然被撤销归档，但「**请求池必须能说出出处**」这条纪律是**通用的**——
换个场景照样成立（同库另一条纪律「机制活下来、口径随线走」）。故守卫留在活着的测试目录里。

为什么**不能** import 被测模块：
它第 48 行 `from eval_engine.core.search_step import (...)`，而 `search_step.py` 已被
`git rm`、**磁盘上不存在**（只在 git 历史里）。故这里用 **ast 解析源码**取常量与结构——
对"归档且不可导入"的代码，这是唯一能真跑的验证方式。
代价必须写明：**它只验证结构与字段，不验证运行时行为。**

背景（为什么需要这个守卫）：
本仓库对**下游产物**的出处是强制的——
`test_bands_file_carries_provenance_and_covers_templates` 断言合格线文件必须带
`provenance.verbatim`（「合格线必须留出处」）。但**上游输入（请求池）此前一个出处字段都没有**。
上游比下游更该留出处，本测试补上这一环。

⚠️ 被测文件在 `reports/` 内，而 `reports/` 被 `.gitignore` 忽略 →
**clone 出来的仓库没有归档副本，整套守卫会跳过**（而不是报 FileNotFoundError）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ARCHIVED = (
    REPO / "reports" / "_revoked_20261003" / "code" / "scripts" / "collect_live_snapshot.py"
)

if not ARCHIVED.exists():
    # 归档副本在 `reports/` 内，而 `reports/` 被 `.gitignore` 忽略 → **clone 出来的仓库没有它**。
    # 此时整套守卫跳过，而不是让测试报 FileNotFoundError。**跳过是有代价的**：守卫不生效。
    pytest.skip(
        "归档副本不在（reports/ 在 .gitignore 内）：请求池出处守卫只在持有归档副本时生效",
        allow_module_level=True,
    )

#: 三支池子的名字 = CLI `--requests` 的取值 = `POOL_PROVENANCE` 的键（三者必须一致）
POOL_TUPLES = {
    "success": "CANDIDATE_REQUESTS",
    "failure": "FAILURE_REQUESTS",
    "semantic": "SEMANTIC_REQUESTS",
}

#: 必填且**非空**。`intents_missing` 非空是刻意的：不写就等于宣称"全覆盖"。
REQUIRED_NON_EMPTY_FIELDS = (
    "status",
    "author",
    "date",
    "text_source",
    "intents_covered",
    "intents_missing",
    "collection_status",
)

#: 必须存在，但**允许为空**（采到了就没有采集缺口）
REQUIRED_MAY_BE_EMPTY_FIELDS = ("collection_gaps",)

#: `collection_status` 是**受控词表**——不许临时编词（本块第一版就编了三个自由字符串）
ALLOWED_COLLECTION_STATUS = (
    "collected",
    "collected_with_environment_noise",
    "attempted_all_failed",
)

ALLOWED_TEXT_SOURCES = (
    "hand_authored",
    "sampled_from_traffic",
    "adapted_from_dataset",
    "mixed",
)

#: 补录必须自曝身份：**推断/有界的出处不得看起来像原始记录**。
#:
#: 2026-10-05 起 `author` 取自 **git 记录**（不再是"未记录"），但 `date` **只是上界**
#: ——池子文件从未提交进仓库，git 给不出提交时间。故 status 仍强调
#: `backfilled` + `bounded`，**不得**写成"已核实"。
BACKFILLED_STATUS = "backfilled_author_from_git_date_bounded"


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
    raise AssertionError(f"源码里找不到模块级常量 {name}（路径：{ARCHIVED}）")


def test_every_pool_has_a_provenance_block():
    provenance = _literal("POOL_PROVENANCE")
    assert set(provenance) == set(POOL_TUPLES), "三支池子必须一一对应，不多不少"
    for pool, tuple_name in POOL_TUPLES.items():
        assert _literal(tuple_name), f"{tuple_name} 不得为空"
        assert pool in provenance


def test_provenance_blocks_are_complete_and_marked_as_backfilled():
    """必填字段齐备；且**补录必须自曝**——推断的出处不能看起来像原始记录。"""
    provenance = _literal("POOL_PROVENANCE")
    for pool, block in provenance.items():
        for field in REQUIRED_NON_EMPTY_FIELDS:
            assert field in block, f"{pool} 缺字段 {field}"
            assert block[field], f"{pool}.{field} 不得为空"
        for field in REQUIRED_MAY_BE_EMPTY_FIELDS:
            assert field in block, f"{pool} 缺字段 {field}（允许为空，但必须在）"
        assert block["text_source"] in ALLOWED_TEXT_SOURCES, f"{pool}.text_source 取值非法"
        assert block["status"] == BACKFILLED_STATUS, (
            f"{pool}.status 必须是 {BACKFILLED_STATUS}——当时没有记录，"
            "补录内容属推断，作者复核前不得当作原始出处引用"
        )
        assert isinstance(block["intents_covered"], list) and block["intents_covered"]


def test_design_gap_and_collection_gap_are_separate_axes():
    """「设计缺口」与「采集缺口」是两件事——混栏则读者分不清**该改题还是该修采集**。

    本块第一版就混了：把「13 条尝试 100% tool_error」写进了设计轴 `intents_missing`。

    - **设计轴** `intents_missing`：**不得为空**（不写等于宣称"全覆盖"）；
    - **采集轴** `collection_gaps`：**允许为空**，但必须与 `collection_status` 一致。
    """
    provenance = _literal("POOL_PROVENANCE")
    for pool, block in provenance.items():
        gaps = block.get("collection_gaps")
        assert isinstance(gaps, list), f"{pool} 缺 collection_gaps（可为空，但必须在）"
        status = block["collection_status"]
        assert status in ALLOWED_COLLECTION_STATUS, f"{pool}.collection_status 取值非法：{status}"
        if status == "collected":
            assert gaps == [], f"{pool} 声称 {status}，就不该有采集缺口条目"
        else:
            assert gaps, f"{pool} 的 collection_status={status}，却没有任何采集缺口条目"
        assert block["intents_missing"], f"{pool}.intents_missing（设计轴）不得为空"


def test_author_is_git_backed_and_date_is_only_a_bound():
    """P2-6：作者取自 **git 记录**（不是推断）；日期**只是上界**。

    依据（2026-10-05 查证）：

    - `git config user.name = guoweihua`；该线提交（`37e397a` 2026-10-01「检索步分栏…」、
      `ace9ff0` / `1920f61` 撤销）作者均为 `guoweihua`（郭伟华）→ **作者有 git 记录**；
    - 池子所在的 `collect_live_snapshot.py` **从未提交**（`git log --all --
      '*collect_live_snapshot*'` 为空）→ git **给不出**提交时间，
      只能取"首次真实采集时刻"（`collected_at`）作上界。

    本测试强制这两点**自曝**：日期必须写成 `≤ …`，且必须给出 `date_basis` 说明
    "为什么只能给上界"。**不得**把上界伪装成精确日期。
    """
    provenance = _literal("POOL_PROVENANCE")
    for pool, block in provenance.items():
        assert "未记录" not in block["author"], f"{pool}.author 已由 git 记录确定"
        assert block["author"].startswith("guoweihua"), f"{pool}.author 应取 git 记录里的提交者"
        assert block["date"].startswith("≤"), (
            f"{pool}.date 必须标成上界（`≤ …`）——池子文件从未提交，git 给不出精确日期"
        )
        assert "上界" in block["date"], f"{pool}.date 须写明「上界」"
        basis = block.get("date_basis") or ""
        assert "从未提交" in basis, f"{pool}.date_basis 必须写明 git 给不出提交时间的原因"
        assert "collected_at" in basis, f"{pool}.date_basis 必须写明上界取自首次采集时刻"


def test_batch_meta_carries_pool_and_pool_provenance():
    """批次 meta 必须留下「本批用了哪支池子、这支池子从哪来」。"""
    keys: set[str] = set()
    for node in ast.walk(_tree()):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Dict)
            and any(isinstance(t, ast.Name) and t.id == "meta" for t in node.targets)
        ):
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
            break
    assert keys, "找不到 `meta = {...}` 字面量"
    assert "pool" in keys, "meta 必须记录本批用的池子名"
    assert "pool_provenance" in keys, "meta 必须带上池子的出处块"


def test_pool_entries_have_stable_shape_and_globally_unique_ids():
    """每条请求都要有 id/style/query；**id 全局唯一**（重复 id 会让下游全部对不上）。"""
    strata = _literal("STRATUM_BY_STYLE")
    seen: dict[str, str] = {}
    for pool, tuple_name in POOL_TUPLES.items():
        for row in _literal(tuple_name):
            assert set(row) == {"id", "style", "query"}, f"{pool} 的条目字段应为 id/style/query"
            assert all(str(row[k]).strip() for k in ("id", "style", "query")), f"{pool} 有空白字段"
            assert row["style"] in strata, f"{pool}/{row['id']} 的 style 不在 STRATUM_BY_STYLE 里"
            assert row["id"] not in seen, (
                f"请求 id 重复：{row['id']}（{seen.get(row['id'])} 与 {pool}）"
            )
            seen[row["id"]] = pool
    assert len(seen) == sum(len(_literal(n)) for n in POOL_TUPLES.values())
