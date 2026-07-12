"""Tests for evaluation gates (baseline & regression)"""
import json

from eval_engine.gates.baseline import BaselineScorer
from eval_engine.gates.regression_gate import RegressionGate


def test_baseline_scorer():
    """BaselineScorer 基础功能"""
    scorer = BaselineScorer()
    assert scorer is not None
    print("✅ BaselineScorer 初始化成功")


def test_baseline_record_and_summary():
    """记录和汇总 Baseline 分数"""
    scorer = BaselineScorer()

    scorer.add_score("faithfulness", 4.5)
    scorer.add_score("faithfulness", 4.0)
    scorer.add_score("helpfulness", 3.5)

    summary = scorer.summarize()
    assert "faithfulness" in summary
    assert summary["faithfulness"]["count"] == 2
    assert summary["faithfulness"]["mean"] == 4.25
    print(f"✅ Baseline 汇总: faith={summary['faithfulness']['mean']}, "
          f"help={summary['helpfulness']['mean']}")


def test_baseline_reset():
    """重置 Baseline"""
    scorer = BaselineScorer()
    scorer.add_score("test", 4.0)
    assert scorer.summarize()["test"]["count"] == 1

    scorer.reset()
    assert scorer.summarize() == {}
    print("✅ Baseline 重置成功")


def test_regression_gate_pass():
    """在 Baseline 内 → 通过"""
    gate = RegressionGate()

    # 先设 baseline
    gate.set_baseline("faithfulness", 4.0, std=0.5)

    # 新分数在 baseline 范围内
    result = gate.check("faithfulness", 3.8)
    assert result["passed"] is True
    print(f"✅ 回归检测通过: score=3.8, baseline=4.0±0.5")


def test_regression_gate_fail():
    """显著低于 Baseline → 触发告警"""
    gate = RegressionGate()

    gate.set_baseline("faithfulness", 4.0, std=0.3)
    result = gate.check("faithfulness", 2.5)

    assert result["passed"] is False
    assert "regression" in result["reason"].lower()
    print(f"✅ 回归检测失败: score=2.5, baseline=4.0±0.3 -> {result['reason']}")


def test_regression_gate_no_baseline():
    """无 Baseline 时默认通过"""
    gate = RegressionGate()
    result = gate.check("unknown_dim", 3.0)
    assert result["passed"] is True
    print("✅ 无 Baseline 默认通过")


if __name__ == "__main__":
    test_baseline_scorer()
    test_baseline_record_and_summary()
    test_baseline_reset()
    test_regression_gate_pass()
    test_regression_gate_fail()
    test_regression_gate_no_baseline()
    print("\n🎉 All gate tests passed!")
