"""
真实 Judge LLM 集成测试 — 需配置 API Key
==========================================

验证 JudgeExecutor 能调用真实 LLM 并返回结构化评分。
无 API Key 时自动跳过。
"""

import os
import json

import pytest


def _has_api_key() -> bool:
    if os.environ.get("JUDGE_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"):
        return True
    if os.environ.get("JUDGE_BASE_URL") and os.environ.get("JUDGE_MODEL"):
        return True
    return False

REQUIRES_API = pytest.mark.skipif(
    not _has_api_key(),
    reason="需要 JUDGE_API_KEY 或 DEEPSEEK_API_KEY 环境变量"
)


@REQUIRES_API
def test_judge_executor_real_llm():
    """JudgeExecutor 用真实 LLM 评分"""
    from eval_engine.judge.executor import JudgeExecutor

    judge = JudgeExecutor()
    prompt = """请对以下回答评分（1-5分）：
    问题：Python 的 sort 函数怎么用？
    回答：sort() 是列表的内置方法，默认升序排序。
    
    输出 JSON 格式：{"score": int, "reasoning": str}"""

    result = judge(prompt)
    assert result is not None
    score = result.get("step_score", result.get("score", None))
    assert score is not None, f"Judge 未返回分数: {result}"
    assert 1 <= score <= 5, f"分数不在 1-5 范围: {score}"
    print(f"✅ 真实 Judge 评分: score={score}")


@REQUIRES_API
def test_judge_executor_with_template():
    """JudgeExecutor + faithfulness 模板"""
    from eval_engine.judge.executor import JudgeExecutor

    judge = JudgeExecutor(template_name="faithfulness")
    prompt = "请基于模板评分标准评估以下回答..."
    result = judge(prompt)
    assert result is not None
    print(f"✅ Judge + 模板: {result.get('step_score', 'N/A')}")
