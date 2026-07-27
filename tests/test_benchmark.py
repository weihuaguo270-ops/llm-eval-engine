"""Tests for benchmark suite and failure taxonomy"""

from eval_engine.benchmark.runner import BenchmarkRunner, load_benchmark_suite
from eval_engine.benchmark.report import format_benchmark_markdown
from eval_engine.core.failure_taxonomy import classify_step_failure, summarize_failures
from eval_engine.core.process_reward import ProcessRewardReport, StepScore, RubricResult
from eval_engine.gates.baseline import BaselineManager, shipped_baseline_path


def test_benchmark_suite_loads():
    suite = load_benchmark_suite()
    assert suite["meta"]["models"]
    assert len(suite["cases"]) >= 32
    print(f"[PASS] benchmark cases={len(suite['cases'])}")


def test_benchmark_runner_offline():
    runner = BenchmarkRunner()
    result = runner.run()
    assert len(result.models) == 3
    assert result.models[0].num_cases >= 32
    md = format_benchmark_markdown(result)
    assert "多模型对比" in md or "Benchmark" in md
    assert result.taxonomy.get("total_failures", 0) >= 1
    print(
        f"[PASS] benchmark run models={len(result.models)} "
        f"failures={result.taxonomy.get('total_failures')}"
    )


def test_failure_taxonomy_hallucination():
    step = StepScore(
        step_index=1,
        step_type="final",
        tool_name=None,
        rubrics=[
            RubricResult(
                dimension="faithfulness",
                criteria="忠实",
                score=1.0,
                reason="幻觉：与观测矛盾",
                needs_revision=True,
            )
        ],
        step_score=1.0,
        needs_revision=True,
    )
    rec = classify_step_failure(step, error_sources=[1], case_id="x")
    assert rec is not None
    assert rec.failure_type == "hallucination"
    print("[PASS] taxonomy hallucination")


def test_failure_taxonomy_propagation():
    step = StepScore(
        step_index=2,
        step_type="final",
        tool_name=None,
        rubrics=[
            RubricResult(
                dimension="general",
                criteria="g",
                score=2.0,
                reason="基于不完整数据",
                needs_revision=True,
            )
        ],
        step_score=2.0,
        needs_revision=True,
    )
    rec = classify_step_failure(step, error_sources=[0], case_id="x")
    assert rec is not None
    assert rec.failure_type == "error_propagation"
    print("[PASS] taxonomy propagation")


def test_shipped_baseline_exists():
    path = shipped_baseline_path()
    assert path.is_file(), path
    bm = BaselineManager(baseline_dir=str(path.parent / "_empty"))
    loaded = bm.load_latest()
    assert loaded is not None
    assert loaded["summary"]["pass_rate"] > 0
    print(f"[PASS] shipped baseline pass_rate={loaded['summary']['pass_rate']}")
