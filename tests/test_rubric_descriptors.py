"""L1：描述符表（criteria × levels × descriptors）与**弃权通道**的测试。

对应业界共识：
- rubric 形状 = criteria / performance levels / descriptors（CMU Eberly、Prometheus 2、Vertex「Rating Rubric」）；
- 「判不出来」必须与「答错」**分开记账**（Inspect AI：`Score.unscored()` → 从指标剔除、coverage 单列），
  **不得**用中位数或任一档顶替。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from eval_engine.judge.calibration import cohens_kappa, extract_judge_score, extract_judge_score_or_none  # noqa: F401
from eval_engine.judge.rubric_descriptors import (
    abstention_json_hint,
    load_descriptors,
    render_scale_anchors,
)

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "src" / "eval_engine" / "dataset" / "data" / "rubric_boundary_line1.json"


# ── 描述符表本身 ─────────────────────────────────────────────

def test_table_covers_every_criterion_and_level():
    d = load_descriptors()
    assert set(d["criteria"]) == {"tool_selection", "faithfulness", "trajectory_safety"}
    for name, spec in d["criteria"].items():
        assert set(spec["levels"]) == {"1", "2", "3", "4", "5"}, name
        for level, desc in spec["levels"].items():
            assert desc.strip(), f"{name} 的 {level} 档没有描述"


def test_descriptors_are_distinct_within_a_criterion():
    """同 criterion 内每档描述必须互不相同，否则等于没有分档。"""
    for name, spec in load_descriptors()["criteria"].items():
        descs = [spec["levels"][l] for l in sorted(spec["levels"], key=int)]
        assert len(set(descs)) == 5, f"{name} 有重复档位描述"


def test_rendered_prompt_contains_all_criteria_levels_and_abstention():
    text = render_scale_anchors()
    for name in ("tool_selection", "faithfulness", "trajectory_safety"):
        assert name in text
    for level in "12345":
        assert f"\n{level} = " in text
    assert "无法判定" in text
    assert ("不得猜测" in text) or ("不要猜" in text)  # 表格用「不得猜测」，输出格式提示用「不要猜」
    assert "unscored" in text  # 记账口径写进提示词


def test_abstention_hint_asks_for_null_and_forbids_guessing():
    hint = abstention_json_hint()
    assert "abstain" in hint and "null" in hint and "不要猜" in hint


def test_rendered_text_matches_descriptor_table_hash():
    """漂移检测：描述符表渲染结果 = 表内记录的指纹（v2.2 是**可选**口径，故指纹记在表里）。"""
    rendered = render_scale_anchors()
    recorded = load_descriptors()["rendered_sha256_16"]
    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:16] == recorded


def test_default_audit_copy_is_still_v21():
    """默认口径未变：审计副本仍是 v2.1，指纹不变（保证与权威快照逐字节可比）。"""
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["version"] == "v2.1"
    assert audit["sha256_16"] == "0a780f5ad7916440"


def test_dataset_meta_keeps_v21_default_and_records_v22_as_optional():
    """默认口径 = v2.1；v2.2 作为**可选**记录在协议里，并写明未过改动门槛。"""
    meta = json.loads(
        (REPO / "src" / "eval_engine" / "dataset" / "data" / "calibration_human_judge.json").read_text(encoding="utf-8")
    )["meta"]
    assert meta["reproducibility"]["rubric_boundary_version"] == "v2.1"
    v22 = [line for line in meta["labeling_protocol"] if line.startswith("v2.2")]
    assert v22 and "JUDGE_RUBRIC=descriptors" in v22[0] and "未通过改动门槛" in v22[0]


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
