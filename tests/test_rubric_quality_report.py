"""Rubric 自检报告（`scripts/rubric_quality_report.py`）的回归测试。

被测的是**两个曾经让结论反向的口径**——都属于本项目最警惕的那类错误
（"两次口径不一致时比大小，会得出方向相反的结论"）：

1. **未标 ≠ Rubric 分歧**：空值是进度信号。把"一人没填"算成"两人判得不一样"，
   会让分歧数虚高、把真正的分档分歧淹没——实测 129 格里 110 格是未标，
   真正的分档分歧只有 5 格。同源错误在 `result_verdict.py` 修过（单列 `not_both`，
   注释写着「踩过」），本报告此前漏了这一步。
2. **退化要按「任一方恒定」判**：只看合并后的取值种类，看不出"只有一方在变"——
   实测把 `query_entity_validity` 报成"不退化"（3 种取值**全部来自 r1**），
   而门禁报"退化"（r2 恒定）。**无数据的一方不算恒定**（那是进度问题）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "rubric_quality_report.py"


def _load():
    """脚本不是包，故按路径加载（与 `test_evidence_path_normalizer.py` 同法）。"""
    spec = importlib.util.spec_from_file_location("rubric_quality_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RQR = _load()


# ── 口径一：未标不是 Rubric 分歧 ──────────────────────────────────────────────


def test_blank_cells_do_not_count_as_criterion_disagreement():
    """一人未填只记 `blank`，不进 Rubric 分歧；真正的分档分歧才进。"""
    rows = [
        {"id": "s1", "d__r1": "4", "d__r2": ""},          # 未填（r2）
        {"id": "s2", "d__r1": "5", "d__r2": ""},          # 未填（r2）
        {"id": "s3", "d__r1": "", "d__r2": "3"},          # 未填（r1，反向）
        {"id": "s4", "d__r1": "na", "d__r2": "unattr"},   # 两种"不判"不同 → 语义分歧
        {"id": "s5", "d__r1": "4", "d__r2": "3"},         # 真分档分歧
    ]
    result = RQR.attribution(rows, ("d",), {}, {})

    assert result["blank_cells"] == 3
    assert result["disagreements_excluding_blank"] == 2
    assert result["disagreements"] == 5, "明细仍保留未标格，便于追溯"
    assert result["kinds"][RQR.BLANK_KIND] == 3
    assert result["kinds"]["Rubric 分档模糊（两人都给了分但档位不同）"] == 1
    assert result["kinds"]["不判语义分歧（一人 na、一人 unattr/oos）"] == 1
    # 未标排到明细最后 → 抽样先看得到真正的分歧
    assert result["detail"][-1]["kind"] == RQR.BLANK_KIND
    assert result["detail"][0]["kind"] != RQR.BLANK_KIND


def test_one_scored_one_deliberately_undecided_is_a_boundary_disagreement():
    """一人给分、一人**有意**判不可判（oos/na/unattr）→ 仍算 Rubric 边界分歧，不算未标。"""
    for token in ("oos", "na", "unattr"):
        result = RQR.attribution([{"id": "s1", "d__r1": "4", "d__r2": token}], ("d",), {}, {})
        assert result["blank_cells"] == 0, f"{token} 是有意的不可判，不是未标"
        assert result["disagreements_excluding_blank"] == 1
        assert RQR.UNSCORED_SEPARATOR in result["kinds"]


def test_agreement_and_double_blank_are_not_disagreements():
    """两人同分、两人都不判、两人都没填 → 一律不是分歧。"""
    rows = [
        {"id": "s1", "d__r1": "4", "d__r2": "4"},
        {"id": "s2", "d__r1": "na", "d__r2": "na"},
        {"id": "s3", "d__r1": "", "d__r2": ""},
    ]
    result = RQR.attribution(rows, ("d",), {}, {})
    assert result["disagreements"] == 0
    assert result["blank_cells"] == 0
    assert result["disagreements_excluding_blank"] == 0


def test_same_band_but_different_failure_code_is_a_disagreement():
    """两人给同一档、但失败码归类不同 → **必须进报告**。

    旧版把 `codes` 比对放在 `a == b → continue` 之后，这一格被**静默丢掉**，
    与 docstring 原意（「分档相同与否先不论，归类不同」）相反。
    这类分歧最该暴露：**严重度一致、归因不一致**——失败码正是可诊断性的载体。
    """
    rows = [{"id": "s1", "d__r1": "4", "d__r2": "4"}]
    left = {"s1": {"d": {"codes": ["missing_slot"]}}}
    right = {"s1": {"d": {"codes": ["verbatim_user_query"]}}}
    result = RQR.attribution(rows, ("d",), left, right)

    assert result["disagreements_excluding_blank"] == 1
    assert result["kinds"] == {"失败码分歧（分档相同与否先不论，归类不同）": 1}


def test_failure_code_mismatch_outranks_band_mismatch():
    """档位与归类都不同时，记「失败码分歧」（更具体的那一类优先）。"""
    rows = [{"id": "s1", "d__r1": "5", "d__r2": "3"}]
    left = {"s1": {"d": {"codes": ["missing_slot"]}}}
    right = {"s1": {"d": {"codes": ["verbatim_user_query"]}}}
    result = RQR.attribution(rows, ("d",), left, right)
    assert result["kinds"] == {"失败码分歧（分档相同与否先不论，归类不同）": 1}


def test_same_band_and_same_code_is_no_disagreement():
    rows = [{"id": "s1", "d__r1": "4", "d__r2": "4"}]
    codes = {"s1": {"d": {"codes": ["missing_slot"]}}}
    assert RQR.attribution(rows, ("d",), codes, codes)["disagreements"] == 0


# ── 口径二：退化 = 任一方恒定 ────────────────────────────────────────────


def test_degenerate_when_either_side_is_constant():
    """一方恒定即退化——旧口径（只看合并取值）会漏掉这种"只有一方在变"。"""
    rows = [
        {"id": "s0", "d__r1": "3", "d__r2": "5"},
        {"id": "s1", "d__r1": "4", "d__r2": "5"},
        {"id": "s2", "d__r1": "5", "d__r2": "5"},
    ]
    item = RQR.discriminative_power(rows, ("d",))["d"]

    assert item["distinct"] == 3                 # 合并后有 3 种取值（全部来自 r1）
    assert item["degenerate_merged"] is False    # 旧口径：看不出问题
    assert item["degenerate"] is True            # 新口径：r2 恒定 → 退化
    assert item["flat_sides"] == ["r2"]
    assert item["by_rater"]["r1"]["distinct"] == 3
    assert item["by_rater"]["r2"]["distinct"] == 1


def test_both_sides_varying_is_not_degenerate():
    rows = [
        {"id": "a", "d__r1": "2", "d__r2": "5"},
        {"id": "b", "d__r1": "4", "d__r2": "3"},
    ]
    item = RQR.discriminative_power(rows, ("d",))["d"]
    assert item["flat_sides"] == []
    assert item["degenerate"] is False


def test_side_without_data_is_not_called_constant():
    """一方完全没标 = 进度问题（反映在 n 上），**不得**当成退化。"""
    rows = [
        {"id": "a", "d__r1": "4", "d__r2": ""},
        {"id": "b", "d__r1": "5", "d__r2": ""},
    ]
    item = RQR.discriminative_power(rows, ("d",))["d"]
    assert item["by_rater"]["r2"]["n"] == 0
    assert item["flat_sides"] == []
    assert item["degenerate"] is False


# ── 防静默降级 ──────────────────────────────────────────────────────────


def test_code_coverage_shape_is_stable_and_counts_recorded_codes():
    """失败码覆盖的结构必须稳定；**规格缺失时 `declared` 为空，不得被读成"没有僵尸条件"**。"""
    sidecar = {"s1": {"d": {"codes": ["missing_slot"]}}}
    report = RQR.code_coverage(("d",), [sidecar])

    assert report["d"]["messages"] == 1
    assert report["d"]["used"] == {"missing_slot": 1}
    if RQR.condition is None:
        # 规格不可导入 → 声明清单读不出来。此时 `never_triggered` 为空
        # **只表示"没算"**；报告消费者必须靠 `spec_available` 区分"没算"与"没有僵尸条件"。
        assert report["d"]["declared"] == []
        assert report["d"]["never_triggered"] == []
    else:
        assert "missing_slot" in report["d"]["declared"]
        assert "missing_slot" not in report["d"]["never_triggered"]


def test_code_channel_separates_not_computed_from_never_exercised():
    """「算不了」与「通道没接通」必须分开报——否则会被读成"没有僵尸条件"。"""
    declared_unused = {"d": {"declared": ["a", "b"], "messages": 0}}

    missing_spec = RQR.code_channel_status(declared_unused, spec_available=False)
    assert missing_spec["declared_total"] == 2
    assert missing_spec["channel_exercised"] is False
    assert "无法计算" in missing_spec["verdict"]

    never_used = RQR.code_channel_status(declared_unused, spec_available=True)
    assert never_used["declared_total"] == 2
    assert never_used["recorded"] == 0
    assert never_used["channel_exercised"] is False
    assert "通道未启用" in never_used["verdict"]

    empty_vocab = RQR.code_channel_status({"d": {"declared": [], "messages": 0}}, True)
    assert empty_vocab["verdict"] == "受控词表为空"

    exercised = RQR.code_channel_status({"d": {"declared": ["a", "b"], "messages": 3}}, True)
    assert exercised["recorded"] == 3
    assert exercised["channel_exercised"] is True
    assert "通道已行使" in exercised["verdict"]


# ── 口径三：冗余证据也要求「两侧都有变异」且 n 足够 ────────────────────────


def test_redundancy_does_not_report_r_below_min_n():
    """n < min_n 时**只报 n** —— 旧实现会在这个规模上把 r 当结论报出来。"""
    rows = [
        {"id": f"s{i}", "a__r1": str(v), "a__r2": str(v), "b__r1": str(v), "b__r2": str(v)}
        for i, v in enumerate(("1", "2", "3"), start=1)
    ]
    item = RQR.redundancy(rows, ("a", "b"), min_n=15)["a×b"]
    assert item["n"] == 3
    assert item["r"] is None, "n=3 的两条维度完全一致，也不得报 r"
    assert item["interpretable"] is False
    assert "n=3" in item["reason"] and "15" in item["reason"]


def test_redundancy_zero_variance_is_a_conclusion_not_missing_data():
    """n 够、但两条维度都恒定 → 零方差是**结论**（没信息），不是"缺数据"。"""
    rows = [
        {"id": f"s{i}", "a__r1": "4", "a__r2": "4", "b__r1": "4", "b__r2": "4"}
        for i in range(20)
    ]
    item = RQR.redundancy(rows, ("a", "b"), min_n=15)["a×b"]
    assert item["n"] == 20
    assert item["r"] is None
    assert item["flat_merged"] is True
    assert item["flat_sides"] == ["r1", "r2"]
    assert item["interpretable"] is False
    assert "零方差" in item["reason"] and "结论" in item["reason"]


def test_redundancy_requires_variation_on_both_sides():
    """只有一方在变时，合并 r 由**单侧**变异驱动 → 不可作为冗余证据（同 κ 的纪律）。"""
    rows = [
        {
            "id": f"s{i}",
            "a__r1": str(1 + i % 5), "a__r2": "5",              # a 只有 r1 在变
            "b__r1": str(1 + i % 5), "b__r2": str(1 + i % 5),   # b 两侧都在变
        }
        for i in range(20)
    ]
    item = RQR.redundancy(rows, ("a", "b"), min_n=15)["a×b"]
    assert item["by_rater"]["r1"]["r"] == 1.0
    assert item["by_rater"]["r2"]["r"] is None
    assert item["by_rater"]["r2"]["flat"] is True
    assert item["flat_sides"] == ["r2"]
    assert item["interpretable"] is False
    assert "单侧" in item["reason"]


def test_numeric_ignores_out_of_scale_values():
    """**刻度外的值按未标处理**（只有 1–5 算分）。

    写测试时踩过：构造数据用了 `2 + i % 5`，会取到 **6**，于是 20 行静默变成 16 行、
    ``n`` 对不上。这不是 bug，是刻度守卫在起作用——所以把它锁成一条显式断言。
    """
    assert RQR._numeric("6") is None
    assert RQR._numeric("0") is None
    assert RQR._numeric("5") == 5.0
    assert RQR._numeric("1") == 1.0
    assert RQR._numeric("") is None
    assert RQR._numeric("na") is None
    assert RQR._numeric("unattr") is None


def test_redundancy_reports_r_when_both_sides_vary_and_n_is_enough():
    """n 够 + 两侧都有变异 → 报 r（两条维度同值构造，故 r 恰为 1.0）。"""
    varied = [
        {
            "id": f"s{i}",
            "a__r1": str(1 + i % 5), "a__r2": str(1 + i % 5),
            "b__r1": str(1 + i % 5), "b__r2": str(1 + i % 5),
        }
        for i in range(20)
    ]
    item = RQR.redundancy(varied, ("a", "b"), min_n=15)["a×b"]
    assert item["n"] == 20, "取值必须落在 1–5 内，否则会被 _numeric 丢掉"
    assert item["r"] == 1.0
    assert item["flat_sides"] == []
    assert item["flat_merged"] is False
    assert item["interpretable"] is True
    assert item["reason"] == ""


def test_redundancy_merged_flat_while_both_sides_vary():
    """两人系统性反向时合并值恒定——**"合并口径不可测"与"该维度没有变异"是两件事**。

    （这个用例是写测试时自己踩出来的：r1 递增、r2 等量递减 → 均值恒为常数。
    当时断言 ``r == 1.0`` 直接失败，才暴露出这两种情形此前共用同一句结论。）
    """
    rows = [
        {
            "id": f"s{i}",
            "a__r1": str(1 + i % 5), "a__r2": str(5 - i % 5),
            "b__r1": str(1 + i % 5), "b__r2": str(5 - i % 5),
        }
        for i in range(20)
    ]
    item = RQR.redundancy(rows, ("a", "b"), min_n=15)["a×b"]
    assert item["n"] == 20
    assert item["flat_merged"] is True, "合并后确实恒定"
    assert item["flat_sides"] == [], "但两侧各自都有变异"
    assert item["r"] is None
    assert item["interpretable"] is False
    assert "系统性反向" in item["reason"]


def test_redundancy_no_common_cell_is_a_progress_problem():
    rows = [{"id": "s1", "a__r1": "4", "a__r2": "", "b__r1": "4", "b__r2": ""}]
    item = RQR.redundancy(rows, ("a", "b"), min_n=15)["a×b"]
    assert item["n"] == 0
    assert item["interpretable"] is False
    assert "进度问题" in item["reason"]
