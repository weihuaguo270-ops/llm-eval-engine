"""结果判断层（常规产出）的回归测试——**常规产出不能悄悄坏掉**。

被测对象：
- `eval_engine.core.verdict.verdict_for` 的判定映射（必须与刻度锚点一致）
- 合格线数据文件**必须留出处**（口径可追溯）
- 聚簇 CI 的边界行为（簇太少会退化 → 已在脚本里设阈值不报）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_engine.core.verdict import clustered_rate_ci, verdict_for

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
