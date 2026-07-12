"""classifier — Task intent classification

Determines whether a user request is a functional test (single-shot execution)
or a generative task (requires iterative eval loop).
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
import re


class TaskType(str, Enum):
    """Task type classification"""
    FUNCTIONAL_TEST = "functional_test"
    GENERATIVE_TASK = "generative_task"
    UNKNOWN = "unknown"


# Patterns that suggest a functional/instrumentation request
_FUNCTIONAL_PATTERNS = [
    r"(?:测试|test|check|验证|verify|试一下|看看|查一下)",
    r"(?:打开|open|start|run|执行|运行)",
    r"(?:几点了|time|date|天气|weather)",
    r"(?:搜索|search|find|look up|查)",
    r"(?:计算|calculate|compute|calc)",
    r"^(?:hi|hello|你好|hey)\s*$",
]


class IntentClassifier:
    """Task intent classifier

    Classifies user requests into task types.
    Uses pattern matching with LLM fallback (configurable).

    Usage:
        classifier = IntentClassifier(llm_classify_fn=optional_llm_fn)
        task_type = classifier.classify("帮我写一份行业报告")
        # → TaskType.GENERATIVE_TASK
    """

    def __init__(self, llm_classify_fn=None):
        self._llm_fn = llm_classify_fn

    def classify(self, user_input: str, context: Optional[dict] = None) -> TaskType:
        """Classify user input into task type

        Args:
            user_input: The user's request text
            context: Optional execution context

        Returns:
            TaskType enum value
        """
        if not user_input or not user_input.strip():
            return TaskType.UNKNOWN

        # Quick pattern check first
        for pattern in _FUNCTIONAL_PATTERNS:
            if re.search(pattern, user_input.strip(), re.IGNORECASE):
                return TaskType.FUNCTIONAL_TEST

        # Longer inputs are typically generative tasks
        if len(user_input) > 30:
            return TaskType.GENERATIVE_TASK

        # LLM fallback if available
        if self._llm_fn:
            try:
                result = self._llm_fn(user_input)
                if result in (TaskType.FUNCTIONAL_TEST, TaskType.GENERATIVE_TASK):
                    return result
            except Exception:
                pass

        # Default: treat as generative task
        return TaskType.GENERATIVE_TASK
