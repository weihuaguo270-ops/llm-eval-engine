"""report — benchmark 多模型对比报告"""

from __future__ import annotations

from typing import Any

from eval_engine.benchmark.runner import BenchmarkRunResult


def format_benchmark_markdown(result: BenchmarkRunResult, title: str = "Benchmark 多模型对比") -> str:
    lines = [
        f"# {title}",
        "",
        f"- 生成时间: `{result.timestamp}`",
        f"- 任务集版本: **v{result.suite_version}**",
        f"- 模型数: **{len(result.models)}**",
        "",
        "## 总览",
        "",
        "| 模型 | 用例数 | 通过率 | 均分 | 平均延迟(ms) | 总 tokens |",
        "|------|------:|-------:|-----:|-------------:|----------:|",
    ]
    for m in result.models:
        lines.append(
            f"| `{m.model}` | {m.num_cases} | {m.pass_rate:.1%} | "
            f"{m.avg_score:.2f} | {m.avg_latency_ms:.0f} | {m.total_tokens} |"
        )

    lines.extend(["", "## 分品类通过率", ""])
    categories: set[str] = set()
    for m in result.models:
        for c in m.cases:
            categories.add(c.category)
    header = "| 品类 | " + " | ".join(f"`{m.model}`" for m in result.models) + " |"
    sep = "|------|" + "|".join(["---:"] * len(result.models)) + "|"
    lines.append(header)
    lines.append(sep)
    for cat in sorted(categories):
        cells = []
        for m in result.models:
            group = [c for c in m.cases if c.category == cat]
            pr = sum(1 for c in group if c.passed) / len(group) if group else 0.0
            cells.append(f"{pr:.0%}")
        lines.append(f"| `{cat}` | " + " | ".join(cells) + " |")

    tax = result.taxonomy or {}
    if tax.get("total_failures", 0) > 0:
        lines.extend(["", "## 失败类型分布（未通过用例）", ""])
        lines.append("| 类型 | 次数 | 占比 |")
        lines.append("|------|-----:|-----:|")
        by_type = tax.get("by_type") or {}
        pct = tax.get("by_type_pct") or {}
        labels = {
            "wrong_tool": "工具选择错误",
            "wrong_params": "参数/调用错误",
            "hallucination": "幻觉/不忠实",
            "error_propagation": "错误传播",
            "inefficient_loop": "冗余/低效",
            "safety_violation": "安全违规",
            "judge_error": "Judge 异常",
            "other": "其他",
        }
        for ftype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            label = labels.get(ftype, ftype)
            lines.append(f"| {label} | {count} | {pct.get(ftype, 0):.1%} |")

    lines.extend(["", "## 逐用例对比", ""])
    case_ids = []
    for m in result.models:
        for c in m.cases:
            if c.case_id not in case_ids:
                case_ids.append(c.case_id)

    hdr = "| 用例 | " + " | ".join(f"`{m.model}` 分/过" for m in result.models) + " |"
    lines.append(hdr)
    lines.append("|------|" + "|".join(["---:"] * len(result.models)) + "|")
    for cid in case_ids:
        cells = []
        for m in result.models:
            match = next((c for c in m.cases if c.case_id == cid), None)
            if match is None:
                cells.append("—")
            else:
                mark = "PASS" if match.passed else "FAIL"
                cells.append(f"{match.overall_score:.1f} {mark}")
        lines.append(f"| `{cid}` | " + " | ".join(cells) + " |")

    lines.append("")
    return "\n".join(lines)


def comparison_table(result: BenchmarkRunResult) -> dict[str, Any]:
    """结构化对比表，供 baseline / 门禁使用。"""
    best = max(result.models, key=lambda m: m.pass_rate) if result.models else None
    return {
        "timestamp": result.timestamp,
        "suite_version": result.suite_version,
        "best_model": best.model if best else None,
        "models": result.to_dict()["models"],
        "failure_taxonomy": result.taxonomy,
    }
