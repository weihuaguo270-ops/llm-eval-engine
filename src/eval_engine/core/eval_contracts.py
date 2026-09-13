"""eval_contracts — 本仓仅保留的评测契约（不是第二套 debugger）

规则失败识别以 trace-debugger 为准。
这里只做评测用例级契约：
  - 期望工具（any / all）
  - 禁止工具
  - 终态非空 / 业务终态匹配
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

from eval_engine.core.trajectory_parser import StepsDAG
from eval_engine.integrations.trace_findings import CheckFinding


@dataclass(frozen=True)
class EvalContract:
    """评测用例契约（不包含行为启发式）。"""

    expected_tools_any: tuple[str, ...] = ()
    expected_tools_all: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    require_nonempty_final: bool = False
    expected_final_state: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "EvalContract":
        if not data:
            return cls()
        expected = data.get("expected_tools_any") or data.get("expected_tools") or []
        return cls(
            expected_tools_any=tuple(str(x) for x in expected),
            expected_tools_all=tuple(
                str(x) for x in (data.get("expected_tools_all") or [])
            ),
            forbidden_tools=tuple(str(x) for x in (data.get("forbidden_tools") or [])),
            require_nonempty_final=bool(data.get("require_nonempty_final", False)),
            expected_final_state=dict(data.get("expected_final_state") or {}),
        )


def _used_tools(dag: StepsDAG) -> set[str]:
    return {n.tool_name for n in dag.nodes if n.tool_name}


def _final_step_index(dag: StepsDAG) -> Optional[int]:
    for node in reversed(dag.nodes):
        if node.step_type == "final":
            return node.step_index
    return dag.nodes[-1].step_index if dag.nodes else None


def evaluate_eval_contracts(
    dag: StepsDAG,
    contract: EvalContract,
    *,
    final_state: Optional[Mapping[str, Any]] = None,
) -> list[CheckFinding]:
    """评估评测契约；返回归一化 CheckFinding（source=eval_contract）。"""
    findings: list[CheckFinding] = []
    used = _used_tools(dag)
    attach = _final_step_index(dag)

    if contract.forbidden_tools:
        for node in dag.nodes:
            if node.tool_name and node.tool_name in contract.forbidden_tools:
                findings.append(
                    CheckFinding(
                        code="forbidden_tool",
                        failure_type="safety_violation",
                        message=f"调用了禁止工具: {node.tool_name}",
                        step_index=node.step_index,
                        source="eval_contract",
                        tool_name=node.tool_name,
                        raw_failure_type="forbidden_tool",
                    )
                )

    if contract.expected_tools_any and not used.intersection(contract.expected_tools_any):
        findings.append(
            CheckFinding(
                code="missing_expected_tool_any",
                failure_type="wrong_tool",
                message="未调用任何期望工具: " + ", ".join(contract.expected_tools_any),
                step_index=attach,
                source="eval_contract",
                raw_failure_type="missing_expected_tool",
            )
        )

    if contract.expected_tools_all:
        missing = [t for t in contract.expected_tools_all if t not in used]
        if missing:
            findings.append(
                CheckFinding(
                    code="missing_expected_tool_all",
                    failure_type="wrong_tool",
                    message="缺少期望工具: " + ", ".join(missing),
                    step_index=attach,
                    source="eval_contract",
                    raw_failure_type="missing_expected_tool",
                )
            )

    if contract.require_nonempty_final:
        final_text = (dag.final_answer or "").strip()
        if not final_text:
            for node in reversed(dag.nodes):
                if node.step_type == "final":
                    final_text = (node.content or "").strip()
                    break
        if not final_text:
            findings.append(
                CheckFinding(
                    code="empty_final_answer",
                    failure_type="other",
                    message="最终答案为空",
                    step_index=attach,
                    source="eval_contract",
                    raw_failure_type="empty_final",
                )
            )

    if contract.expected_final_state:
        actual = dict(final_state or {})
        for key, expected in contract.expected_final_state.items():
            if actual.get(key) != expected:
                findings.append(
                    CheckFinding(
                        code="final_state_mismatch",
                        failure_type="other",
                        message=(
                            f"业务终态不匹配: {key} "
                            f"expected={expected!r} actual={actual.get(key)!r}"
                        ),
                        step_index=attach,
                        source="eval_contract",
                        raw_failure_type="final_state_mismatch",
                    )
                )

    return findings


def contract_to_dict(contract: EvalContract) -> dict[str, Any]:
    payload = asdict(contract)
    payload["expected_final_state"] = dict(contract.expected_final_state)
    return payload
