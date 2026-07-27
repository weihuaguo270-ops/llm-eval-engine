"""benchmark — 固定任务集跑批与多模型对比"""

from eval_engine.benchmark.runner import BenchmarkRunner, BenchmarkRunResult
from eval_engine.benchmark.report import format_benchmark_markdown

__all__ = ["BenchmarkRunner", "BenchmarkRunResult", "format_benchmark_markdown"]
