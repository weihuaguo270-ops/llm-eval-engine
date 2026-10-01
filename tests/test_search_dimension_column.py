"""检索步维度分栏：结构性约束 + 未校准状态

这一组测试锁的是"两栏不得合并"这条治理约束，不是数值本身。
"""

from __future__ import annotations

import pytest

from eval_engine.core.multimodal_process_judge import DIMENSIONS as MEDIA_DIMENSIONS
from eval_engine.core.search_step import (
    SEARCH_DIMENSION_CRITERIA,
    SEARCH_DIMENSIONS,
    is_search_step,
    is_search_tool,
)
from eval_engine.gates.search_calibration import (
    SEARCH_KAPPA_UNIT,
    STATUS_CALIBRATED,
    STATUS_UNCALIBRATED,
    search_calibration_column,
)


def _row(episode_id, step_index, dimension, human, judge, split="held_out", **extra):
    row = {
        "episode_id": episode_id,
        "step_index": step_index,
        "dimension": dimension,
        "split": split,
        "human_score": human,
        "judge_score": judge,
    }
    row.update(extra)
    return row


def test_search_dimensions_are_disjoint_from_media_pin():
    assert set(SEARCH_DIMENSIONS).isdisjoint(set(MEDIA_DIMENSIONS))
    assert len(SEARCH_DIMENSIONS) == 4


def test_every_search_dimension_has_criteria():
    for name in SEARCH_DIMENSIONS:
        assert name in SEARCH_DIMENSION_CRITERIA
        assert len(SEARCH_DIMENSION_CRITERIA[name]) > 20


def test_is_search_tool_matches_common_and_cjk_names():
    for name in (
        "web_search",
        "Web_Search",
        "search_docs",
        "google_search",
        "通用搜索工具",
        "检索工具",
    ):
        assert is_search_tool(name) is True, name
    for name in ("calculator", "execute_python", "", None):
        assert is_search_tool(name) is False


def test_is_search_step_reads_mapping_and_no_tool():
    assert is_search_step({"tool_name": "web_search"}) is True
    assert is_search_step({"action": {"name": "web_search"}}) is True
    assert is_search_step({"tool_name": "calculator"}) is False
    assert is_search_step(None) is False


def test_uncalibrated_column_reports_no_kappa_number():
    """没有 held-out 样本时不得出现任何 κ 数值，但分栏必须可见。"""
    column = search_calibration_column(None)
    assert column["status"] == STATUS_UNCALIBRATED
    assert column["kappa"] is None
    assert column["n"] == 0
    assert column["needs_calibration"] is None
    assert column["kappa_unit"] == SEARCH_KAPPA_UNIT
    assert column["kappa_unit"] != "dimension_cell"
    assert column["dimensions"] == list(SEARCH_DIMENSIONS)


def test_calibrated_column_keeps_its_own_unit_and_dimensions():
    rows = [
        _row("ep-1", 0, "query_quality", 4, 4),
        _row("ep-1", 0, "result_utilization", 5, 4),
        _row("ep-1", 0, "fallback_behavior", 2, 2),
        _row("ep-2", 1, "citation_grounding", 3, 3),
    ]
    column = search_calibration_column(rows)
    assert column["status"] == STATUS_CALIBRATED
    assert column["n"] == 4
    assert column["kappa_unit"] == SEARCH_KAPPA_UNIT
    assert column["dimensions"] == list(SEARCH_DIMENSIONS)
    assert isinstance(column["kappa"], float)
    assert column["bootstrap"] is not None
    assert column["episode_count"] == 2
    assert column["gate_split"] == "held_out"


def test_media_dimension_rows_are_rejected():
    """媒体维度串进检索分栏必须直接失败，不能静默混算。"""
    with pytest.raises(ValueError):
        search_calibration_column([_row("ep-1", 0, "media_timing", 4, 4)])


def test_non_held_out_rows_do_not_enter_the_column():
    rows = [
        _row("ep-1", 0, "query_quality", 4, 4, split="dev"),
        _row("ep-2", 0, "query_quality", 5, 5),
    ]
    column = search_calibration_column(rows)
    assert column["n"] == 1
    assert column["episode_ids"] == ["ep-2"]
