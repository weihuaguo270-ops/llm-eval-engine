"""证据完整性报告的回归测试（失败成簇 / 快照寿期 / meta 对账 / 覆盖报告 / 来源集中度 / 拒绝留档）。

与另两个守卫测试不同：`scripts/evidence_integrity_report.py` 位于**活着的** `scripts/`，
**不依赖任何被撤销的模块**，故这里可以直接 importlib 按路径加载并**调用真函数**，
不需要 ast 取函数那套办法。

核心要锁住的一句话：**`n_samples` 从来不是独立单位**。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "evidence_integrity_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("evidence_integrity_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EIR = _load()


# ── 窗口切分：按**间隔**切，不按钟表切 ──────────────────────────────────────


def test_group_windows_splits_on_gaps_not_on_clock():
    """同一次事故落一个窗口；相隔十几小时的两次事故必须分开。

    用固定 epoch 值构造，避免依赖本机时区/当前时间。
    """
    base = 1_800_000_000.0  # 任意基准
    one_incident = [base, base + 60, base + 120, base + 300]
    assert len(EIR.group_windows(one_incident, 30)) == 1

    two_incidents = one_incident + [base + 13 * 3600, base + 13 * 3600 + 90]
    windows = EIR.group_windows(two_incidents, 30)
    assert len(windows) == 2
    assert len(windows[0]) == 4 and len(windows[1]) == 2

    # 阈值可调：把窗口收到 1 分钟，第一段也会被拆开
    assert len(EIR.group_windows(one_incident, 1)) > 1
    assert EIR.group_windows([], 30) == []


# ── 失败成簇：独立单位是请求与事故，不是样本 ────────────────────────────────


def _failing_batch():
    """复刻真实批次的形状：25 条 tool_error 来自 16 个请求、挤在 2 个时间窗。"""
    samples = []
    # 窗口一同日 10:07–10:12，8 个请求共 13 条
    plan_a = [("f01", 2), ("f02", 2), ("f03", 1), ("f04", 1), ("f05", 1), ("f06", 2), ("f07", 2), ("f08", 1)]
    for index, (case, count) in enumerate(plan_a):
        for k in range(count):
            samples.append({
                "case_id": case,
                "collected_at": f"2026-10-02T10:{7 + index:02d}:{k * 10:02d}",
                "outcome_stratum": "tool_error",
                "provenance": "own_live_collection",
            })
    # 窗口二隔日 23:27–23:33，8 个请求共 12 条
    plan_b = [("g01", 2), ("g02", 1), ("g03", 2), ("g04", 2), ("g05", 1), ("g06", 1), ("g07", 2), ("g08", 2)]
    for index, (case, count) in enumerate(plan_b):
        for k in range(count):
            samples.append({
                "case_id": case,
                "collected_at": f"2026-10-02T23:{27 + index:02d}:{k * 10:02d}",
                "outcome_stratum": "tool_error",
                "provenance": "own_live_collection",
            })
    # 另有成功样本，不得被算进失败
    samples.append({"case_id": "w01", "collected_at": "2026-10-01T20:16:36",
                    "outcome_stratum": "success", "provenance": "own_live_collection"})
    return samples


def test_failure_clusters_reports_requests_and_windows_not_samples():
    samples = _failing_batch()

    result = EIR.failure_clusters(samples, window_minutes=30)

    assert result["n_failing_samples"] == 25
    assert result["n_requests"] == 16
    assert result["n_windows"] == 2, "两次事故相隔约 13 小时，必须分开"
    assert result["max_samples_per_request"] == 2
    assert all(row["n_samples"] > 0 for row in result["windows"])
    assert sum(row["n_samples"] for row in result["windows"]) == 25
    assert "16 个请求" in result["independent_units_note"]
    assert "2 个时间窗" in result["independent_units_note"]


def test_failure_clusters_is_empty_safe():
    result = EIR.failure_clusters([], window_minutes=30)
    assert result["n_failing_samples"] == 0
    assert result["n_requests"] == 0
    assert result["n_windows"] == 0
    assert result["max_samples_per_request"] == 0


# ── 快照寿期：声明优先，推算要标注来源 ──────────────────────────────────────


def _write_manifest(tmp_path: Path, entries) -> Path:
    batch = tmp_path / "batch"
    batch.mkdir(parents=True, exist_ok=True)
    (batch / "snapshots_manifest.json").write_text(
        json.dumps({"snapshots": entries}, ensure_ascii=False), encoding="utf-8"
    )
    return batch


def test_snapshot_freshness_prefers_declared_and_labels_derived(tmp_path):
    """声明值与推算值**含义不同**，必须分开计数报出。"""
    batch = _write_manifest(tmp_path, [
        {  # 采集时就声明了寿期
            "snapshot_id": "w01_20261001T201636",
            "collected_at": "2026-10-01T20:16:36",
            "snapshot_policy": {"review_by": "2026-12-30", "recollectable": False},
        },
        {  # 没有声明 → 按 CLI 间隔推算
            "snapshot_id": "f01_20261002T100748",
            "collected_at": "2026-10-02T10:07:48",
        },
    ])

    result = EIR.snapshot_freshness(batch, [], review_interval_days=90, today="2026-10-05")

    assert result["policy_source_counts"] == {"declared": 1, "derived": 1, "unknown": 0}
    assert result["n_overdue"] == 0
    assert result["oldest"] == "2026-10-01T20:16:36"
    assert result["newest"] == "2026-10-02T10:07:48"


def test_snapshot_freshness_flags_overdue_and_counts_days(tmp_path):
    batch = _write_manifest(tmp_path, [
        {"snapshot_id": "old", "collected_at": "2026-08-18T13:08:53",
         "snapshot_policy": {"review_by": "2026-09-01"}},
    ])

    result = EIR.snapshot_freshness(batch, [], review_interval_days=90, today="2026-10-05")

    assert result["n_overdue"] == 1
    overdue = result["overdue"][0]
    assert overdue["snapshot_id"] == "old"
    assert overdue["review_by"] == "2026-09-01"
    assert overdue["policy_source"] == "declared"
    assert overdue["days_left"] < 0


def test_snapshot_freshness_falls_back_to_samples_when_manifest_missing(tmp_path):
    """没有清单时退回样本身份表——**但不能因此声称"没有快照"**。"""
    batch = tmp_path / "empty"
    batch.mkdir()
    samples = [{"snapshot_id": "s1", "collected_at": "2026-10-02T10:07:12"}]

    result = EIR.snapshot_freshness(batch, samples, review_interval_days=90, today="2026-10-05")

    assert result["n_snapshots"] == 1
    assert result["policy_source_counts"]["derived"] == 1


# ── meta 对账：抓"硬编码键导致静默丢行" ─────────────────────────────────────


def test_reconcile_detects_rows_silently_lost_by_hardcoded_keys():
    samples = (
        [{"outcome_stratum": "success"}] * 51
        + [{"outcome_stratum": "tool_error"}] * 25
        + [{"outcome_stratum": "no_content"}] * 4
    )
    meta = {"outcome_strata": {"success": 51, "failure": 0}}  # 旧版的真实产物

    result = EIR.reconcile_outcome_strata(meta, samples)

    assert result["consistent"] is False
    assert result["declared_total"] == 51 and result["actual_total"] == 80
    assert result["missing_from_meta"] == {"tool_error": 25, "no_content": 4}


def test_reconcile_passes_on_consistent_meta():
    samples = [{"outcome_stratum": "a"}] * 2 + [{"outcome_stratum": "b"}]
    meta = {"outcome_strata": {"a": 2, "b": 1}}
    assert EIR.reconcile_outcome_strata(meta, samples)["consistent"] is True


# ── 覆盖率报告：在不在 ──────────────────────────────────────────────────────


def test_coverage_report_state_absent_then_present(tmp_path):
    absent = EIR.coverage_report_state(tmp_path)
    assert absent["present"] is False
    assert "P0-2" in absent["note"]

    (tmp_path / "collection_coverage.json").write_text(
        json.dumps({"ok": False, "problems": ["层被清空：['ambiguous']"],
                    "empty_strata": ["ambiguous"], "zero_sample_requests": ["w12"]},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    present = EIR.coverage_report_state(tmp_path)
    assert present["present"] is True and present["ok"] is False
    assert present["empty_strata"] == ["ambiguous"]


# ── 端到端：main() 能跑通并落盘 ─────────────────────────────────────────────


def test_main_writes_all_four_sections(tmp_path):
    batch = tmp_path / "batch"
    batch.mkdir()
    samples = _failing_batch() + [
        {"case_id": "w02", "collected_at": "2026-10-01T20:17:51",
         "outcome_stratum": "success", "provenance": "own_live_collection"},
    ]
    (batch / "search_steps.json").write_text(
        json.dumps(
            {"meta": {"outcome_strata": {"success": 2, "tool_error": 25}}, "samples": samples},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "report.json"

    exit_code = EIR.main(["--batch", str(batch), "--out", str(out), "--today", "2026-10-05"])

    assert exit_code == 0, "本脚本只报告、不判定门禁，必须退出 0"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload) >= {
        "failure_clusters", "snapshot_freshness",
        "outcome_strata_reconciliation", "coverage_report",
    }
    assert payload["failure_clusters"]["n_windows"] == 2
    assert payload["coverage_report"]["present"] is False
    assert set(payload) >= {"source_concentration", "rejection_ledger", "truncation_evidence"}
    assert payload["rejection_ledger"]["present"] is False, "该批次早于 P2-1"


# ── P2-3：来源集中度（三档必须分开） ────────────────────────────────────────


def test_source_concentration_separates_no_evidence_from_single_source():
    """**0 域名是证据缺失，1 域名才是「来源集中」**——混了就是两个口径混成一个数。"""
    samples = [
        {"case_id": "no_ev", "observation": "工具报错：SSL 握手超时"},
        {
            "case_id": "single",
            "observation": "1. A 链接: https://a.example.com/x 2. A 链接: http://www.a.example.com/y",
        },
        {
            "case_id": "multi",
            "observation": "1. A 链接: https://a.example.com/ 2. B 链接: https://b.example.org/",
        },
    ]

    result = EIR.source_concentration(samples, min_domains=2)

    assert result["n_requests"] == 3
    assert result["counts"] == {"no_evidence": 1, "single_source": 1, "multi_source": 1}
    assert result["no_evidence"] == ["no_ev"]
    assert result["single_source"] == ["single"]
    assert result["multi_source"] == ["multi"]


def test_source_concentration_normalizes_www_prefix():
    """`www.a.example.com` 与 `a.example.com` 是**同一站点**——不去前缀会把单一来源误判成多来源。"""
    samples = [{
        "case_id": "c",
        "observation": "https://www.a.example.com/1  https://a.example.com/2",
    }]

    result = EIR.source_concentration(samples)

    assert result["counts"]["single_source"] == 1
    assert result["domains_by_request"]["c"] == ["a.example.com"]


def test_source_concentration_does_not_read_the_sources_field():
    """域名从 **`observation`** 抽，不是 `sources`。

    实测依据：归档批次 80/80 样本的 `sources` 都形如
    `[{"case_id": …, "variant": …}]`——它记的是「样本来自哪个请求/变体」，**不含 URL**。
    """
    samples = [{
        "case_id": "c",
        "sources": [{"case_id": "c", "variant": "live_snapshot"}],
        "observation": "无任何链接的文本",
    }]

    result = EIR.source_concentration(samples)

    assert result["counts"]["no_evidence"] == 1, "sources 里的 case_id 不得被当成 URL"


# ── P2-1 活侧：拒绝留档在不在 ───────────────────────────────────────────────


def test_rejection_ledger_state_absent_then_present(tmp_path):
    absent = EIR.rejection_ledger_state(tmp_path)
    assert absent["present"] is False
    assert "P2-1" in absent["note"]

    (tmp_path / "rejection_ledger.json").write_text(
        json.dumps(
            {
                "counts_by_category": {"limit_not_selected": 3, "no_search_step": 3},
                "entries": [{"id": "w12"}],
                "not_visible_here": {"under_specified": "出题阶段才能判定"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    present = EIR.rejection_ledger_state(tmp_path)
    assert present["present"] is True and present["readable"] is True
    assert present["counts_by_category"]["limit_not_selected"] == 3
    assert present["n_entries"] == 1
    assert present["not_visible_here"] == ["under_specified"]


# ── P3-1：材料截断（**下界**估计） ─────────────────────────────────────────


def test_truncation_evidence_counts_only_samples_at_the_limit():
    """只有**恰好达到上限**才算被截断——小于上限不能说明任何事，故结果是**下界**。"""
    samples = [
        {"case_id": "a", "observation": "x" * 500, "final_answer": "y" * 1000},
        {"case_id": "b", "observation": "x" * 499, "final_answer": "y" * 999},
        {"case_id": "c", "observation": "", "final_answer": ""},
    ]

    result = EIR.truncation_evidence(
        samples, limits={"observation": 500, "final_answer": 1000}
    )

    observation = result["by_field"]["observation"]
    assert observation["at_limit_samples"] == 1, "只有 a 恰好 500"
    assert observation["at_limit_share"] == round(1 / 3, 3)
    assert observation["example_cases"] == ["a"]
    assert observation["max_length"] == 500
    assert result["by_field"]["final_answer"]["at_limit_samples"] == 1
    assert result["n_samples"] == 3
    assert "下界" in result["note"]


def test_truncation_defaults_come_from_the_upstream_recorder():
    """默认上限来自**上游记录器**（500 / 1000），不是本仓随手定的。"""
    assert EIR.DEFAULT_TRUNCATION_LIMITS == {"observation": 500, "final_answer": 1000}
