"""Tests for evaluation gates — 基于真实 API"""
from eval_engine.gates.baseline import BaselineManager
from eval_engine.gates.regression_gate import RegressionGate


def test_baseline_manager_init():
    mgr = BaselineManager()
    assert mgr is not None
    print("✅ BaselineManager 初始化")


def test_baseline_save_and_load():
    mgr = BaselineManager()
    report = {"summary": {"overall_score": 4.5, "num_steps": 10}}
    path = mgr.save(report)
    assert path is not None
    loaded = mgr.load_latest()
    assert loaded is not None
    score = loaded.get("summary", {}).get("overall_score", 0)
    assert score == 4.5
    print(f"✅ save/load: overall_score={score}")


def test_baseline_compare():
    mgr = BaselineManager()
    mgr.save({"summary": {"overall_score": 4.0, "num_steps": 10}})
    result = mgr.compare({"overall_score": 3.5, "pass_rate": 0.8})
    assert "baseline_found" in result
    assert "regression_detected" in result
    print(f"✅ compare: baseline_found={result['baseline_found']}")


def test_baseline_list():
    mgr = BaselineManager()
    mgr.save({"summary": {"overall_score": 4.0, "num_steps": 5}})
    baselines = mgr.list_baselines(limit=5)
    assert len(baselines) > 0
    print(f"✅ list_baselines: {len(baselines)} entries")


def test_regression_gate_evaluate():
    gate = RegressionGate()
    result = gate.evaluate({"overall_score": 4.5, "pass_rate": 0.9})
    assert "passed" in result
    assert "message" in result
    print(f"✅ evaluate: passed={result['passed']}")


def test_regression_gate_threshold():
    gate = RegressionGate()
    assert hasattr(gate, "threshold")
    print(f"✅ threshold={gate.threshold}")


if __name__ == "__main__":
    test_baseline_manager_init()
    test_baseline_save_and_load()
    test_baseline_compare()
    test_baseline_list()
    test_regression_gate_evaluate()
    test_regression_gate_threshold()
    print("\n🎉 All gate tests passed (real API)")
