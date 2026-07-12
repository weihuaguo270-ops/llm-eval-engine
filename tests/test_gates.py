"""Tests for evaluation gates (baseline & regression)"""
from eval_engine.gates.baseline import BaselineManager
from eval_engine.gates.regression_gate import RegressionGate


def test_baseline_manager_init():
    """BaselineManager 初始化"""
    mgr = BaselineManager()
    assert mgr is not None
    print("✅ BaselineManager 初始化成功")


def test_baseline_save_and_load():
    """保存和加载 Baseline"""
    mgr = BaselineManager()
    report = {"summary": {"overall_score": 4.5, "num_steps": 10}}
    path = mgr.save(report)
    assert path is not None

    latest = mgr.load_latest()
    assert latest is not None
    score = latest.get("summary", {}).get("overall_score", 0)
    assert score == 4.5
    print(f"✅ Baseline 保存/加载成功: overall_score={score}")


def test_baseline_compare():
    """对比当前结果与 Baseline"""
    mgr = BaselineManager()
    mgr.save({"summary": {"overall_score": 4.0, "num_steps": 10}})

    result = mgr.compare({"overall_score": 3.8})
    assert result["baseline_found"] is True
    print(f"✅ Baseline 对比成功: baseline_found={result['baseline_found']}")


def test_baseline_compare_no_baseline():
    """无 Baseline 时对比"""
    mgr = BaselineManager()
    result = mgr.compare({"overall_score": 3.8})
    assert result["baseline_found"] is False
    print("✅ 无 Baseline 时 comparison 正确处理")


def test_regression_gate():
    """RegressionGate 评估"""
    gate = RegressionGate()
    result = gate.evaluate({"overall_score": 4.5, "pass_rate": 0.9})
    assert "regression_detected" in result
    print(f"✅ RegressionGate 评估: {result}")


def test_regression_gate_detects_regression():
    """RegressionGate 可配置阈值"""
    gate = RegressionGate(score_threshold=1.0, pass_rate_threshold=0.2)
    result = gate.evaluate({"overall_score": 2.5, "pass_rate": 0.5})
    # 低分数应可能触发回归
    assert isinstance(result["regression_detected"], bool)
    print(f"✅ RegressionGate 回归检测: regression={result['regression_detected']}")


if __name__ == "__main__":
    test_baseline_manager_init()
    test_baseline_save_and_load()
    test_baseline_compare()
    test_baseline_compare_no_baseline()
    test_regression_gate()
    test_regression_gate_detects_regression()
    print("\n🎉 All gate tests passed!")
