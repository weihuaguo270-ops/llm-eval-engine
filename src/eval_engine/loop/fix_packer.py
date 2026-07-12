"""fix_packer — 将低分项打包为结构化修正指令

供 Eval Loop 在检测到低分步骤时使用。
将 ProcessRewardReport 中的失败步骤转为 LLM 能理解的修正反馈。
"""

from __future__ import annotations
from typing import Any


def pack_revision_instructions(
    report: Any,
    dag: Any,
    max_issues: int = 5,
) -> str:
    """将评分报告中的低分项打包为结构化修正指令

    Args:
        report: ProcessRewardReport 对象
        dag: StepsDAG 对象，包含步骤的上下文信息
        max_issues: 最多报告的问题数

    Returns:
        格式化的修正指令字符串，可直接注入 LLM 的上下文
    """
    if not report or not report.per_step:
        return ""

    failed_steps = [s for s in report.per_step if s.needs_revision]

    if not failed_steps:
        return ""

    lines = []
    lines.append(f"评估发现 {len(failed_steps)} 个步骤需要修正：")
    lines.append("")

    for i, step in enumerate(failed_steps[:max_issues]):
        lines.append(f"--- 问题 {i + 1}: Step {step.step_index} ({step.step_type}) ---")
        if step.tool_name:
            lines.append(f"工具: {step.tool_name}")
        lines.append(f"步骤评分: {step.step_score:.2f}")

        # 列出低分维度
        low_rubrics = [r for r in step.rubrics if r.needs_revision]
        if low_rubrics:
            lines.append("不达标维度:")
            for r in low_rubrics:
                lines.append(f"  - [{r.dimension}] {r.criteria}")
                lines.append(f"    得分: {r.score}, 理由: {r.reason}")

        lines.append("")

    if len(failed_steps) > max_issues:
        lines.append(f"... 还有 {len(failed_steps) - max_issues} 个问题未列出")

    return "\n".join(lines)
