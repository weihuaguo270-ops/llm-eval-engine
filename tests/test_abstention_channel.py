"""弃权通道（abstention）的**记账**测试。

判不出来必须与答错**分开记账**（Inspect AI：`Score.unscored()` → 从指标剔除、coverage 单列），
**不得**用中位数或任一档顶替。
"""

from __future__ import annotations

import pytest

from eval_engine.judge.calibration import extract_judge_score, extract_judge_score_or_none  # noqa: F401


# ── 弃权通道的记账 ───────────────────────────────────────────

def test_abstention_extracts_to_none_not_a_score():
    assert extract_judge_score_or_none({"score": None, "abstain": True, "reason": "材料不足"}) is None
    assert extract_judge_score_or_none({"abstain": True}) is None
    # 明确要求不得用任一档顶替
    assert extract_judge_score_or_none({"score": None, "abstain": True}) != 3.0


def test_unparseable_is_none_not_midpoint():
    assert extract_judge_score_or_none({}) is None
    assert extract_judge_score_or_none({"score": "null"}) is None
    assert extract_judge_score_or_none({"score": "N/A"}) is None
    assert extract_judge_score_or_none({"rubrics": [{"score": None}]}) is None


def test_normal_scores_still_parse():
    assert extract_judge_score_or_none({"score": 4}) == pytest.approx(4.0)
    assert extract_judge_score_or_none({"rubrics": [{"score": 3}, {"score": 5}]}) == pytest.approx(4.0)
    assert extract_judge_score_or_none({"step_score": 2}) == pytest.approx(2.0)


def test_legacy_extractor_keeps_its_documented_fallback():
    """历史行为**保留**（解析失败 → 3.0），以免破坏既有调用；live 校准路径已改用新函数。"""
    assert extract_judge_score({}) == pytest.approx(3.0)
