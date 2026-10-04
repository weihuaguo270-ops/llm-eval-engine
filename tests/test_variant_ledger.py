"""口径变体选择防护（通用规则 + 检查）的测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_engine.judge import variant_ledger as vl


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    p = tmp_path / "ledger.json"
    monkeypatch.setattr(vl, "LEDGER_PATH", p)
    return p


def test_first_adopt_fingerprint_is_allowed_and_recorded(ledger):
    d = vl.check_and_record("ds@v5/held_out", "aaaa")
    assert d["allowed"] and not d["selection"]
    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert saved["batches"]["ds@v5/held_out"]["fingerprints"]["aaaa"]["runs"] == 1


def test_same_fingerprint_repeat_is_allowed(ledger):
    vl.check_and_record("ds@v5/held_out", "aaaa")
    d = vl.check_and_record("ds@v5/held_out", "aaaa")
    assert d["allowed"] and "重复" in d["reason"]


def test_second_different_fingerprint_is_refused(ledger):
    """★ 规则本体：同一批上的第二个口径变体 = 选择 → 默认拒绝。"""
    vl.check_and_record("ds@v5/held_out", "aaaa")
    d = vl.evaluate("ds@v5/held_out", "bbbb")
    assert not d["allowed"]
    assert "不得第二次用于选择口径" in d["reason"] or "同一批" in d["reason"]


def test_explicit_optin_allows_but_marks_selection(ledger):
    vl.check_and_record("ds@v5/held_out", "aaaa")
    d = vl.check_and_record("ds@v5/held_out", "bbbb", allow_selection=True)
    assert d["allowed"] and d["selection"] is True
    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert saved["batches"]["ds@v5/held_out"]["fingerprints"]["bbbb"]["selection_use"] is True


def test_probe_purpose_is_allowed_and_not_selection(ledger):
    """故意造坏的对照（验证指标灵敏度）不产生『采纳哪个口径』的选择 → 允许。"""
    vl.check_and_record("ds@v5/held_out", "aaaa")
    d = vl.check_and_record("ds@v5/held_out", "broken1", purpose="probe")
    assert d["allowed"] and d["selection"] is False


def test_different_batch_is_independent(ledger):
    vl.check_and_record("ds@v5/held_out", "aaaa")
    d = vl.evaluate("ds@v5/dev", "bbbb")
    assert d["allowed"]


def test_record_is_idempotent_and_counts_runs(ledger):
    vl.record("ds@v5/held_out", "aaaa")
    vl.record("ds@v5/held_out", "aaaa")
    vl.record("ds@v5/held_out", "aaaa")
    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert saved["batches"]["ds@v5/held_out"]["fingerprints"]["aaaa"]["runs"] == 3


def test_batch_key_shape():
    assert vl.batch_key("calibration_human_judge", 5, "held_out") == "calibration_human_judge@v5/held_out"
    assert vl.batch_key(None, None, None) == "unknown@v?/all"
