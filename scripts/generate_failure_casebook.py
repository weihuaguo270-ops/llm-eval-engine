"""从 benchmark offline 跑批结果生成 failure_casebook.md"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_engine.benchmark.runner import BenchmarkRunner
from eval_engine.core.failure_taxonomy import classify_step_failure

OUT = ROOT / "docs" / "failure_casebook.md"


def main() -> None:
    runner = BenchmarkRunner()
    result = runner.run()
    entries = []
    for m in result.models:
        for c in m.cases:
            if c.passed:
                continue
            for step in c.report.per_step:
                rec = classify_step_failure(
                    step,
                    error_sources=c.error_sources,
                    case_id=c.case_id,
                )
                if rec is None:
                    continue
                entries.append({
                    "case_id": c.case_id,
                    "model": m.model,
                    "category": c.category,
                    "query": c.query[:80],
                    "step_index": rec.step_index,
                    "failure_type": rec.failure_type,
                    "step_score": rec.step_score,
                    "is_root_cause": rec.is_root_cause,
                    "reason": rec.reason,
                    "error_sources": c.error_sources,
                })

    # 去重并取前 15
    seen = set()
    unique = []
    for e in entries:
        key = (e["case_id"], e["model"], e["step_index"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    unique.sort(key=lambda x: (x["failure_type"], x["step_score"]))

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

    lines = [
        "# 失败案例库（Failure Casebook）",
        "",
        f"- 生成方式：benchmark offline 跑批自动提取",
        f"- 失败条目数：**{len(unique)}**",
        "",
        "## 案例列表",
        "",
    ]
    for i, e in enumerate(unique[:15], 1):
        label = labels.get(e["failure_type"], e["failure_type"])
        root = "是" if e["is_root_cause"] else "否"
        lines.extend([
            f"### {i}. `{e['case_id']}` / `{e['model']}`",
            "",
            f"- **品类**: {e['category']}",
            f"- **失败类型**: {label}",
            f"- **根因步**: Step {e['step_index']}（根因: {root}）",
            f"- **得分**: {e['step_score']}/5",
            f"- **传播源头**: {e['error_sources']}",
            f"- **任务**: {e['query']}",
            f"- **原因**: {e['reason']}",
            "",
        ])

    lines.extend([
        "## 复现",
        "",
        "```bash",
        "python scripts/generate_failure_casebook.py",
        "python examples/run_benchmark.py",
        "```",
        "",
    ])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({min(15, len(unique))} cases shown, {len(unique)} total failures)")


if __name__ == "__main__":
    main()
