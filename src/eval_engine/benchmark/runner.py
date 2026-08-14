"""runner — 固定 benchmark 任务集跑批"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from eval_engine.core.failure_taxonomy import summarize_failures
from eval_engine.core.process_reward import (
    ProcessRewardReport,
    ProcessRewardScorer,
    analyze_error_propagation,
)
from eval_engine.core.trajectory_parser import parse_trajectory

DEFAULT_SUITE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "dataset",
    "data",
    "benchmark_suite.json",
)


@dataclass
class CaseResult:
    """单个模型变体在一个固定任务上的过程评分结果。"""

    case_id: str
    category: str
    query: str
    passed: bool
    overall_score: float
    pass_rate: float
    num_failed_steps: int
    error_sources: list[int]
    latency_ms: int
    tokens: int
    report: ProcessRewardReport
    error_analysis: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRunResult:
    """同一模型在当前任务集上的全部结果及聚合指标。"""

    model: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def num_cases(self) -> int:
        """返回该模型实际执行的用例数。"""
        return len(self.cases)

    @property
    def pass_count(self) -> int:
        """返回同时满足过程修订标记和得分阈值的用例数。"""
        return sum(1 for c in self.cases if c.passed)

    @property
    def pass_rate(self) -> float:
        """返回执行用例内的通过比例；空运行返回零。"""
        return self.pass_count / self.num_cases if self.num_cases else 0.0

    @property
    def avg_score(self) -> float:
        """返回用例等权平均过程得分。"""
        if not self.cases:
            return 0.0
        return sum(c.overall_score for c in self.cases) / len(self.cases)

    @property
    def avg_latency_ms(self) -> float:
        """返回用例记录延迟的算术平均值。"""
        if not self.cases:
            return 0.0
        return sum(c.latency_ms for c in self.cases) / len(self.cases)

    @property
    def total_tokens(self) -> int:
        """返回任务集记录的总 token 数。"""
        return sum(c.tokens for c in self.cases)


@dataclass
class BenchmarkRunResult:
    """可序列化的跨模型 benchmark 运行证据。"""

    suite_version: int
    models: list[ModelRunResult]
    taxonomy: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """生成报告层使用的稳定字典结构。"""
        return {
            "timestamp": self.timestamp,
            "suite_version": self.suite_version,
            "models": [
                {
                    "model": m.model,
                    "num_cases": m.num_cases,
                    "pass_count": m.pass_count,
                    "pass_rate": round(m.pass_rate, 4),
                    "avg_score": round(m.avg_score, 3),
                    "avg_latency_ms": round(m.avg_latency_ms, 1),
                    "total_tokens": m.total_tokens,
                    "by_category": _aggregate_by_category(m.cases),
                    "cases": [
                        {
                            "case_id": c.case_id,
                            "category": c.category,
                            "passed": c.passed,
                            "overall_score": c.overall_score,
                            "pass_rate": round(c.pass_rate, 4),
                            "num_failed_steps": c.num_failed_steps,
                            "error_sources": c.error_sources,
                            "latency_ms": c.latency_ms,
                            "tokens": c.tokens,
                        }
                        for c in m.cases
                    ],
                }
                for m in self.models
            ],
            "failure_taxonomy": self.taxonomy,
        }


def _aggregate_by_category(cases: list[CaseResult]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[CaseResult]] = {}
    for c in cases:
        buckets.setdefault(c.category, []).append(c)
    out: dict[str, dict[str, Any]] = {}
    for cat, group in buckets.items():
        n = len(group)
        out[cat] = {
            "num_cases": n,
            "pass_rate": round(sum(1 for x in group if x.passed) / n, 4),
            "avg_score": round(sum(x.overall_score for x in group) / n, 3),
        }
    return out


def load_benchmark_suite(path: Optional[str] = None) -> dict[str, Any]:
    """加载固定任务集；结构完整性由运行器消费时校验。"""
    path = path or DEFAULT_SUITE_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _frozen_judge_from_variant(variant: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    """用 variant 内预填 step_scores 构造逐步 Judge（离线可复现）。"""
    scores: list[dict[str, Any]] = variant.get("step_judge_outputs") or []
    call_idx = {"n": 0}

    def judge_fn(prompt: str) -> dict[str, Any]:
        i = call_idx["n"]
        call_idx["n"] += 1
        if i < len(scores):
            return scores[i]
        return {
            "role_understanding": "fallback",
            "rubrics": [{"dimension": "general", "score": 3.0, "reason": "无预填分"}],
            "step_score": 3.0,
            "needs_revision": False,
        }

    return judge_fn


class BenchmarkRunner:
    """固定任务集跑批器。

    默认使用 benchmark_suite.json 内各 model variant 的冻结 step 分数（offline）。
    """

    def __init__(self, suite_path: Optional[str] = None, min_step_score: float = 3.5):
        self.suite_path = suite_path or DEFAULT_SUITE_PATH
        self.suite = load_benchmark_suite(self.suite_path)
        self.min_step_score = min_step_score

    @property
    def models(self) -> list[str]:
        """返回任务集声明的模型标识，保留清单顺序。"""
        return list(self.suite.get("meta", {}).get("models", []))

    def run(
        self,
        models: Optional[list[str]] = None,
        *,
        judge_fn: Optional[Callable[[str, str], dict[str, Any]]] = None,
    ) -> BenchmarkRunResult:
        """对指定模型跑批并生成过程得分与失败分类。

        未传 ``judge_fn`` 时读取任务集内冻结的逐步分数，结果可离线
        复现；传入时调用 ``judge_fn(model, prompt)``，属于 live Judge
        证据。用例仅在无需修订且总分达到 ``min_step_score`` 时通过。
        """
        target_models = models or self.models
        cases = self.suite.get("cases", [])
        model_results: list[ModelRunResult] = []
        taxonomy_inputs: list[tuple[str, str, ProcessRewardReport]] = []

        for model in target_models:
            mr = ModelRunResult(model=model)
            for case in cases:
                variant = (case.get("variants") or {}).get(model)
                if not variant:
                    continue
                trajectory = variant["trajectory"]
                dag = parse_trajectory(trajectory)

                if judge_fn is not None:
                    step_judge = lambda p, m=model: judge_fn(m, p)  # noqa: E731
                else:
                    step_judge = _frozen_judge_from_variant(variant)

                scorer = ProcessRewardScorer(
                    judge_fn=step_judge,
                    min_step_score=self.min_step_score,
                )
                t0 = time.perf_counter()
                report = scorer.score_trajectory(dag, fast_mode=False)
                elapsed = int((time.perf_counter() - t0) * 1000)
                err = analyze_error_propagation(report, dag)
                passed = not report.needs_revision and report.overall_score >= self.min_step_score

                cr = CaseResult(
                    case_id=case["id"],
                    category=case.get("category", "unknown"),
                    query=case.get("query", ""),
                    passed=passed,
                    overall_score=report.overall_score,
                    pass_rate=report.pass_rate,
                    num_failed_steps=report.num_failed_steps,
                    error_sources=report.error_sources,
                    latency_ms=variant.get("latency_ms", elapsed),
                    tokens=variant.get("tokens", 0),
                    report=report,
                    error_analysis=err,
                )
                mr.cases.append(cr)
                if not passed:
                    taxonomy_inputs.append((case["id"], case.get("category", "unknown"), report))
            model_results.append(mr)

        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        taxonomy = summarize_failures(taxonomy_inputs).to_dict()
        return BenchmarkRunResult(
            suite_version=int(self.suite.get("meta", {}).get("version", 1)),
            models=model_results,
            taxonomy=taxonomy,
            timestamp=ts,
        )


def default_suite_path() -> str:
    return os.path.abspath(DEFAULT_SUITE_PATH)
