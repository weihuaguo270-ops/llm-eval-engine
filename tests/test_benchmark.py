"""Tests for benchmark suite and failure taxonomy"""

from eval_engine.benchmark.runner import (
    BenchmarkRunner,
    CaseResult,
    ModelRunResult,
    _aggregate_by_category,
    load_benchmark_suite,
)
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


def _case(case_id: str, score, *, passed: bool, category: str = "tool") -> CaseResult:
    report = ProcessRewardReport(
        query="q",
        per_step=[],
        overall_score=score,
        num_steps=0,
        num_scored=0 if score is None else 1,
        num_failed_steps=0,
        error_sources=[],
        needs_revision=not passed,
        healing_log=[],
        dag_summary={},
    )
    return CaseResult(
        case_id=case_id,
        category=category,
        query="q",
        passed=passed,
        overall_score=score,
        pass_rate=1.0 if passed else 0.0,
        num_failed_steps=0,
        error_sources=[],
        latency_ms=1,
        tokens=1,
        report=report,
    )


def test_avg_score_skips_unscored_cases():
    """未评估的用例不进均值分母：把"没评过"当 0 分会凭空压低平均分。"""
    run = ModelRunResult(
        model="m",
        cases=[
            _case("scored-1", 4.0, passed=True),
            _case("scored-2", 5.0, passed=True),
            _case("unscored", None, passed=False),
        ],
    )

    assert run.num_cases == 3, "未评估仍是执行过的用例"
    assert run.avg_score == 4.5, "只对两个已评分用例取均值"
    assert run.pass_rate == 2 / 3


def test_category_avg_score_skips_unscored_cases():
    """分类聚合与整体聚合必须同口径：未评估不进分母，也不变成 0。"""
    grouped = _aggregate_by_category(
        [
            _case("a", 3.0, passed=True, category="tool"),
            _case("b", None, passed=False, category="tool"),
            _case("c", None, passed=False, category="rag"),
        ]
    )

    assert grouped["tool"]["num_cases"] == 2
    assert grouped["tool"]["avg_score"] == 3.0
    assert grouped["rag"]["num_cases"] == 1
    assert grouped["rag"]["avg_score"] == 0.0, "一个都没评上时返回 0.0 而不是崩"


def test_shipped_baseline_exists():
    path = shipped_baseline_path()
    assert path.is_file(), path
    bm = BaselineManager(baseline_dir=str(path.parent / "_empty"))
    loaded = bm.load_latest()
    assert loaded is not None
    assert loaded["summary"]["pass_rate"] > 0
    print(f"[PASS] shipped baseline pass_rate={loaded['summary']['pass_rate']}")
