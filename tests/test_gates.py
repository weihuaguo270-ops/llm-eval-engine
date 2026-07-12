"""Tests for evaluation gates (baseline & regression)"""
from eval_engine.gates.baseline import BaselineManager
from eval_engine.gates.regression_gate import RegressionGate


def test_baseline_manager():
    """BaselineManager 初始化"""
    mgr = BaselineManager()
    assert mgr is not None
    print("✅ BaselineManager 初始化成功")


def test_baseline_save_and_load():
    """保存和加载 Baseline"""
    mgr = BaselineManager()
    report = {"faithfulness": {"mean": 4.5, "count": 10}}
    path = mgr.save(report)
    assert path is not None

    loaded = mgr.load_latest()
    assert loaded is not None
    assert loaded["faithfulness"]["mean"] == 4.5
    print(f"✅ Baseline 保存/加载成功: mean={loaded['faithfulness']['mean']}")


def test_baseline_compare():
    """对比当前报告与 Baseline"""
    mgr = BaselineManager()
    mgr.save({"faithfulness": {"mean": 4.0, "std": 0.5, "count": 10}})

    current = {"faithfulness": {"mean": 3.8, "std": 0.4, "count": 5}}
    diff = mgr.compare(current)

    assert "faithfulness" in diff
    print(f"✅ Baseline 对比: delta={diff['faithfulness'].get('delta', 'N/A')}")


def test_regression_gate_pass():
    """在 Baseline 内 → 通过"""
    gate = RegressionGate()
    gate.set_baseline("faithfulness", 4.0, std=0.5)
    result = gate.check("faithfulness", 3.8)
    assert result["passed"] is True
    print(f"✅ 回归检测通过: score=3.8, baseline=4.0±0.5")


def test_regression_gate_fail():
    """显著低于 Baseline → 触发告警"""
    gate = RegressionGate()
    gate.set_baseline("faithfulness", 4.0, std=0.3)
    result = gate.check("faithfulness", 2.5)
    assert result["passed"] is False
    print(f"✅ 回归检测失败: score=2.5, baseline=4.0±0.3")


def test_regression_gate_no_baseline():
    """无 Baseline 时默认通过"""
    gate = RegressionGate()
    result = gate.check("unknown_dim", 3.0)
    assert result["passed"] is True
    print("✅ 无 Baseline 默认通过")


if __name__ == "__main__":
    test_baseline_manager()
    test_baseline_save_and_load()
    test_baseline_compare()
    test_regression_gate_pass()
    test_regression_gate_fail()
    test_regression_gate_no_baseline()
    print("\n🎉 All gate tests passed!")
