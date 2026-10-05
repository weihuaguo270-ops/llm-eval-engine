"""结果判断层（常规产出）的回归测试——**常规产出不能悄悄坏掉**。

被测对象：
- `eval_engine.core.verdict.verdict_for` 的判定映射（必须与刻度锚点一致）
- 合格线数据文件**必须留出处**（口径可追溯）
- 聚簇 CI 的边界行为（簇太少会退化 → 已在脚本里设阈值不报）
- **合格线加载器只有一份**（在 `core.verdict`）：外壳键 `bands` 与 `verdict_bands`
  必须解析出同一张表——否则同一份内容会读出**不同判定**
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from eval_engine.core.verdict import (
    clustered_rate_ci,
    load_bands,
    load_bands_document,
    verdict_for,
)

REPO = Path(__file__).resolve().parents[1]
BANDS_FILE = REPO / "src" / "eval_engine" / "dataset" / "data" / "verdict_bands_line1.json"


def test_verdict_mapping_follows_scale_anchors():
    """defect=1–2｜marginal=3｜pass=4–5｜弃权=undecidable｜空=blank｜未定义合格线=unbanded。"""
    bands = {"t": {"pass_min": 4, "marginal_min": 3}}
    assert verdict_for("t", "5", bands) == "pass"
    assert verdict_for("t", "4", bands) == "pass"
    assert verdict_for("t", "3", bands) == "marginal"
    assert verdict_for("t", "2", bands) == "defect"
    assert verdict_for("t", "1", bands) == "defect"
    assert verdict_for("t", "na", bands) == "undecidable"
    assert verdict_for("t", "unattr", bands) == "undecidable"
    assert verdict_for("t", "", bands) == "blank"          # 未标 ≠ 合格
    assert verdict_for("t", "4", {}) == "unbanded"         # 没定义合格线 ≠ 合格


def test_bands_file_carries_provenance_and_covers_templates():
    payload = json.loads(BANDS_FILE.read_text(encoding="utf-8"))
    assert "刻度锚点" in payload["provenance"]["verbatim"], "合格线必须留出处（逐字引用锚点）"
    assert payload["provenance"]["field"] == "meta.labeling_protocol"
    for template, band in payload["bands"].items():
        assert band["pass_min"] == 4 and band["marginal_min"] == 3
        assert template in payload["defect_definition"], f"{template} 缺缺陷定义"


def test_clustered_rate_ci_bounds_and_degeneracy():
    """率 CI 必须落在 [0,1]；**簇极少时区间会退化**（脚本据此设阈值不报）。"""
    low, high = clustered_rate_ci({"a": 1, "b": 0}, {"a": 1, "b": 1}, n_boot=200)
    assert 0.0 <= low <= high <= 1.0
    # 单簇 → 重采样无变化 → 退化
    low1, high1 = clustered_rate_ci({"only": 1}, {"only": 2}, n_boot=200)
    assert low1 == high1 == pytest.approx(0.5)


def test_load_bands_accepts_flat_and_wrapped_shapes(tmp_path):
    """合格线表两种外层结构都要吃得下。

    外壳结构（``{"verdict_bands": {...}, "rulings_version": ...}``）曾让**整表静默变成
    `unbanded`**：旧实现把整份文档当合格线表，每个维度都取不到，而且不报错——
    缺陷率全 0 会被误读成「零缺陷」。这里同时锁住"元数据不得当成维度"。
    """
    flat = {"d": {"pass_min": 4, "marginal_min": 3, "defect": "x"}}
    wrapped = {
        "note": "重建版",
        "rulings_version": "v19",
        "verdict_bands": flat,
        "convention": "4–5 合格",
    }
    for payload in (flat, wrapped):
        path = tmp_path / "bands.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        bands = load_bands(path)
        assert bands == flat, "两种外层结构必须解析出同一张表"
        assert "note" not in bands and "rulings_version" not in bands, "元数据不是维度"
        assert verdict_for("d", "4", bands) == "pass"
        assert verdict_for("d", "2", bands) == "defect"
        assert verdict_for("d", "4", {}) == "unbanded"

    assert load_bands(tmp_path / "missing.json") == {}
    not_an_object = tmp_path / "list.json"
    not_an_object.write_text("[1, 2]", encoding="utf-8")
    assert load_bands(not_an_object) == {}


def test_load_bands_reads_the_tracked_wrapper_key_too(tmp_path):
    """**回归测试**：外壳键 `bands`（被跟踪文件用的那个）必须与 `verdict_bands` 解析出同一张表。

    实测 bug：同一份内容、同一个维度、同一个 5 分——

    - 键名 `bands` → 读成 `unbanded`
    - 键名 `verdict_bands` → 读成 `pass`

    判定只差一个键名，**且两边都不报错**：旧实现把整份文档当维度表，
    返回非空 → 调用方那句「未加载到任何合格线」的告警不会触发。
    """
    inner = {"tool_selection": {"pass_min": 4, "marginal_min": 3, "defect": "1–2"}}
    document = {
        "bands": inner,
        "provenance": {"field": "meta.labeling_protocol", "verbatim": "4–5 合格"},
        "derivation": "逐字引用刻度锚点",
    }
    path = tmp_path / "line1.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    bands = load_bands(path)

    assert bands == inner, "外壳键 bands 必须与 verdict_bands 解析出同一张表"
    assert verdict_for("tool_selection", "5", bands) == "pass"
    assert verdict_for("tool_selection", "2", bands) == "defect"


def test_load_bands_document_keeps_metadata(tmp_path):
    """维度层与元数据必须**分得开**：判定要维度层，可追溯性要整份文档。"""
    document = {
        "bands": {"d": {"pass_min": 4}},
        "provenance": {"field": "meta.labeling_protocol", "verbatim": "4–5 合格"},
        "derivation": "逐字引用",
    }
    path = tmp_path / "line1.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    assert load_bands(path) == {"d": {"pass_min": 4}}
    loaded = load_bands_document(path)
    assert loaded["provenance"]["verbatim"] == "4–5 合格"
    assert loaded["derivation"] == "逐字引用"
    assert load_bands_document(tmp_path / "missing.json") == {}


def test_load_bands_flat_drops_entries_that_are_not_bands(tmp_path):
    """兜底（扁平）**只收像合格线的条目**（含 `pass_min`）——否则元数据会被当成维度。"""
    path = tmp_path / "flat.json"
    path.write_text(
        json.dumps(
            {
                "d": {"pass_min": 4, "marginal_min": 3},
                "note": "这条是元数据，不是维度",
                "provenance": {"field": "x"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert load_bands(path) == {"d": {"pass_min": 4, "marginal_min": 3}}


def test_example_script_has_no_local_bands_loader():
    """收敛守卫：`examples/run_result_evaluation.py` **不得**再自带一份加载器。

    两份加载器曾对同一概念用两种外壳键，导致同一份内容读出不同判定（见回归测试）。
    这条把它钉在**结构层**：再长出一份，测试就挂。
    """
    source = (REPO / "examples" / "run_result_evaluation.py").read_text(encoding="utf-8")
    defined = {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef)
    }
    assert "load_bands" not in defined, "合格线加载器统一在 core.verdict，不得在 examples 里再定义一份"
