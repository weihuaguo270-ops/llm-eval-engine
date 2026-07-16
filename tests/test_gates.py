"""Tests for evaluation gates — 基于真实 API"""
from eval_engine.gates.baseline import BaselineManager
from eval_engine.gates.regression_gate import RegressionGate


def test_baseline_manager_init(tmp_path):
    mgr = BaselineManager(str(tmp_path))
    assert mgr is not None
    print("✅ BaselineManager 初始化")


def test_baseline_save_and_load(tmp_path):
    mgr = BaselineManager(str(tmp_path))
    # save() 读取的是顶层的 overall_score，不是 summary 内部的
    report = {
        "overall_score": 4.5,
        "summary": {"pass_rate": 0.9, "num_steps": 10, "num_failed_steps": 0}
    }
    path = mgr.save(report)
    assert path is not None
    loaded = mgr.load_latest()
    assert loaded is not None
    score = loaded.get("summary", {}).get("overall_score", 0)
    print(f"✅ save/load: overall_score={score}")


def test_baseline_compare(tmp_path):
    mgr = BaselineManager(str(tmp_path))
    mgr.save({"overall_score": 4.0, "summary": {"pass_rate": 0.85, "num_steps": 10}})
    result = mgr.compare({"overall_score": 3.5, "pass_rate": 0.8})
    assert "baseline_found" in result
    print(f"✅ compare: baseline_found={result['baseline_found']}")


def test_baseline_list(tmp_path):
    mgr = BaselineManager(str(tmp_path))
    mgr.save({"overall_score": 4.0, "summary": {"pass_rate": 0.8, "num_steps": 5}})
    baselines = mgr.list_baselines(limit=5)
    assert len(baselines) > 0
    print(f"✅ list_baselines: {len(baselines)} entries")


def test_regression_gate_evaluate(tmp_path):
    gate = RegressionGate(BaselineManager(str(tmp_path)))
    result = gate.evaluate({"overall_score": 4.5, "pass_rate": 0.9})
    assert "passed" in result
    assert "message" in result
    print(f"✅ evaluate: passed={result['passed']}")
