"""search_step — 检索步的维度定义与工具名分派

与 ``core/multimodal_step.py`` 同形态：先判定"这一步是不是检索步"，
再由本模块的维度表给出可判定的评分维度，供 Judge / 人工校准使用。

边界（重要，勿混）：

- 本模块评的是**检索步的动作与结果处理质量**（查询是否切题、结果是否被后续
  利用、失败时有无备选、引用是否与本步结果对应），**不评最终答案的忠实度**——
  那是 ``context_faithfulness`` 的职责。两处不得对同一事实重复打分。
- 这里是**维度定义**，不等于已校准的能力。分栏与口径见
  ``eval_engine/gates/search_calibration.py`` 与
  ``docs/search_dimension_column_20261001.md``；在拿到 held-out 人工校准样本前，
  **不得对外引用任何 κ 数值**。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

# 工具名约定；与 trace-debugger 的 is_search_tool 保持同一套语义：
# 子串匹配 "search"、限定包含 "搜索"，再叠加显式名单。
SEARCH_TOOL_NAMES = frozenset(
    {
        "web_search",
        "search",
        "search_web",
        "google_search",
        "bing_search",
        "search_api",
        "news_search",
        "image_search",
        "video_search",
        "search_docs",
        "search_knowledge_base",
        "knowledge_search",
        "rag_search",
        "retrieve",
        "retrieval",
    }
)
_SEARCH_SUBSTRINGS = ("search",)
_SEARCH_CJK_HINTS = ("搜索", "检索")

# 检索步过程维度。单位与分栏见 gates/search_calibration.py。
SEARCH_DIMENSIONS = (
    "query_quality",
    "result_utilization",
    "fallback_behavior",
    "citation_grounding",
)

SCALE = (
    "评分刻度（整数 1–5）：1=失败/危险；2=明显不当；3=勉强可用；"
    "4=基本正确；5=符合协议。不适用时记 null，不计入 κ。"
)

SEARCH_DIMENSION_CRITERIA: dict[str, str] = {
    "query_quality": (
        "本步构造的检索查询是否切题：是否包含回答所需的关键限定"
        "（对象、时间、地区、版本、单位），而不是把用户原句原样丢进去。"
        "边界：查询词写得好但返回结果差 → 本维度不扣分，结果质量不在本维度；"
        "空查询、把实体名写错、编造不存在的标识 → 1–2。"
    ),
    "result_utilization": (
        "返回结果是否被后续步骤真正使用：正确摘取、正确引用、或在结果不可用时"
        "明确放弃；被完全忽略、或引用了返回内容里根本没有的信息 → 1–2。"
        "边界：只看本步结果与后续动作之间的连续性，不评最终答案的组织与文风。"
    ),
    "fallback_behavior": (
        "空结果 / 超时 / 结构过弱时是否有补偿动作：换查询词、换工具、放宽或收窄"
        "范围、或明确声明依据不足；无任何补偿动作却继续给出结论 → 1–2。"
        "边界：一次检索即成功时本维度给 5（无须补偿），不得因「没有 fallback」扣分。"
    ),
    "citation_grounding": (
        "被本步结果支撑的内容在引用时是否有据：引用确实来自本步返回，且不越界"
        "外推；引用不存在的结果、或把弱相关结果说成结论依据 → 1–2。"
        "边界：答案级忠实度（是否添加了观测里没有的结论）属 "
        "``context_faithfulness``；本维度只判「引用与本步返回结果的对应关系」。"
    ),
}


def is_search_tool(name: Optional[str]) -> bool:
    """按名称规则判断工具是否属于检索类（大小写不敏感）。"""
    raw = name or ""
    text = raw.strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in {n.lower() for n in SEARCH_TOOL_NAMES}:
        return True
    if any(sub in lowered for sub in _SEARCH_SUBSTRINGS):
        return True
    return any(hint in raw for hint in _SEARCH_CJK_HINTS)


def is_search_step(node: Any) -> bool:
    """StepNode / 映射均可；无工具名的步骤不是检索步。"""
    if node is None:
        return False
    if isinstance(node, Mapping):
        tool = node.get("tool_name") or node.get("action")
        if isinstance(tool, Mapping):
            tool = tool.get("name")
        return is_search_tool(str(tool) if tool else None)
    return is_search_tool(getattr(node, "tool_name", None))


def dimension_criteria() -> dict[str, str]:
    """返回本分栏的维度→判定标准（供 prompt 组装 / 文档引用）。"""
    return dict(SEARCH_DIMENSION_CRITERIA)
