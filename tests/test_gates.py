"""Tests for evaluation gates (baseline & regression)"""
from eval_engine.gates.baseline import BaselineManager
from eval_engine.gates.regression_gate import RegressionGate


def test_baseline_manager_init():
    mgr = BaselineManager()
    assert mgr is not None
    print("✅ BaselineManager 初始化成功")


def test_baseline_save_and_load():
    mgr = BaselineManager()
    report = {"summary": {"overall_score": 4.5, "num_steps": 10}}
    path = mgr.save(report)
    assert path is not None

    latest = mgr.load_latest()
    score = latest.get("summary", {}).get("overall_score", 0) if latest else 0
    print(f"✅ Baseline 保存/加载: score={score}")


def test_baseline_compare():
    mgr = BaselineManager()
    mgr.save({"summary": {"overall_score": 4.0, "num_steps": 10}})
    result = mgr.compare({"overall_score": 3.8})
    assert "baseline_found" in result
    print(f"✅ Baseline 对比: baseline_found={result.get('baseline_found')}")


def test_regression_gate_evaluate():
    gate = RegressionGate()
    result = gate.evaluate({"overall_score": 4.5, "pass_rate": 0.9})
    assert "passed" in result
    assert "message" in result
    print(f"✅ RegressionGate 评估: passed={result['passed']}")


def test_regression_gate_with_custom_threshold():
    gate = RegressionGate(threshold=0.5)
    result = gate.evaluate({"overall_score": 4.5, "pass_rate": 0.9})
    assert "passed" in result
    print(f"✅ RegressionGate 自定义阈值: threshold={gate.threshold}")


if __name__ == "__main__":
    test_baseline_manager_init()
    test_baseline_save_and_load()
    test_baseline_compare()
    test_regression_gate_evaluate()
    test_regression_gate_with_custom_threshold()
    print("\n🎉 All gate tests passed!")
