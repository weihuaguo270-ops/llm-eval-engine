"""Run supported Agent SDKs and export their native execution evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, TypedDict


def run_langgraph_expense_episode(claim_id: str = "C-1") -> dict[str, Any]:
    """Execute a real LangGraph StateGraph and return importable node records."""
    from langgraph.graph import END, START, StateGraph

    class ExpenseState(TypedDict):
        claim_id: str
        status: str
        nodes: list[dict[str, Any]]

    def inspect_claim(state: ExpenseState) -> dict[str, Any]:
        record = {
            "node_name": "inspect_claim",
            "thought": "check claim before approval",
            "tool": "get_claim",
            "tool_payload": {"claim_id": state["claim_id"]},
            "tool_result": {"status": "pending"},
        }
        return {"status": "pending", "nodes": [*state["nodes"], record]}

    def approve_claim(state: ExpenseState) -> dict[str, Any]:
        record = {
            "node_name": "approve_claim",
            "thought": "approve the verified claim",
            "tool": "approve_claim",
            "tool_payload": {"claim_id": state["claim_id"]},
            "tool_result": {"status": "approved"},
        }
        return {"status": "approved", "nodes": [*state["nodes"], record]}

    builder = StateGraph(ExpenseState)
    builder.add_node("inspect_claim", inspect_claim)
    builder.add_node("approve_claim", approve_claim)
    builder.add_edge(START, "inspect_claim")
    builder.add_edge("inspect_claim", "approve_claim")
    builder.add_edge("approve_claim", END)
    result = builder.compile().invoke(
        {"claim_id": claim_id, "status": "new", "nodes": []}
    )
    return {
        "run_id": f"langgraph-{claim_id}",
        "task": f"approve expense claim {claim_id}",
        "inputs": {"claim_id": claim_id},
        "outputs": {"status": result["status"]},
        "nodes": result["nodes"],
        "expected_state": {"claim": {"status": "approved"}},
        "final_state": {"claim": {"status": result["status"]}},
        "metadata": {"runtime": "langgraph.StateGraph"},
    }


@dataclass
class _OpenAIRunEvidence:
    trace_id: str = ""
    spans: list[dict[str, Any]] = field(default_factory=list)


async def run_openai_agents_expense_episode(claim_id: str = "C-1") -> dict[str, Any]:
    """Execute the Agents SDK with a deterministic local model and capture SDK spans."""
    from agents import (
        Agent,
        Model,
        ModelResponse,
        Runner,
        TracingProcessor,
        function_tool,
        set_trace_processors,
    )
    from agents.usage import Usage
    from openai.types.responses import (
        ResponseFunctionToolCall,
        ResponseOutputMessage,
        ResponseOutputText,
    )

    class LocalExpenseModel(Model):
        async def get_response(
            self,
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            **_kwargs,
        ):
            has_tool_output = isinstance(input, list) and any(
                isinstance(item, dict) and item.get("type") == "function_call_output"
                for item in input
            )
            if has_tool_output:
                output = [ResponseOutputMessage(
                    id="message-1",
                    content=[ResponseOutputText(
                        annotations=[], text="claim approved", type="output_text"
                    )],
                    role="assistant", status="completed", type="message",
                )]
            else:
                output = [ResponseFunctionToolCall(
                    arguments=json.dumps({"claim_id": claim_id}),
                    call_id="approve-call-1",
                    name="approve_claim",
                    type="function_call",
                )]
            return ModelResponse(output=output, usage=Usage(), response_id="local-1")

        async def stream_response(self, *_args, **_kwargs):
            if False:
                yield None
            raise NotImplementedError

    evidence = _OpenAIRunEvidence()

    class EvidenceProcessor(TracingProcessor):
        def on_trace_start(self, trace) -> None:
            evidence.trace_id = trace.trace_id

        def on_trace_end(self, _trace) -> None:
            return None

        def on_span_start(self, _span) -> None:
            return None

        def on_span_end(self, span) -> None:
            exported = span.export()
            if exported:
                evidence.spans.append(exported)

        def shutdown(self) -> None:
            return None

        def force_flush(self) -> None:
            return None

    @function_tool
    def approve_claim(claim_id: str) -> dict[str, str]:
        """Approve an expense claim by identifier."""
        return {"claim_id": claim_id, "status": "approved"}

    processor = EvidenceProcessor()
    set_trace_processors([processor])
    agent = Agent(
        name="expense-approver",
        instructions="Approve the requested claim with the available tool.",
        model=LocalExpenseModel(),
        tools=[approve_claim],
    )
    try:
        result = await Runner.run(agent, f"approve expense claim {claim_id}")
    finally:
        set_trace_processors([])
    spans = [_normalize_openai_span(span) for span in evidence.spans]
    return {
        "trace_id": evidence.trace_id,
        "task": f"approve expense claim {claim_id}",
        "input": f"approve expense claim {claim_id}",
        "output": result.final_output,
        "spans": spans,
        "expected_state": {"claim": {"status": "approved"}},
        "final_state": {"claim": {"status": "approved"}},
        "metadata": {
            "runtime": "openai-agents.Runner",
            "model": "deterministic-local-test-model",
        },
    }


def _normalize_openai_span(span: dict[str, Any]) -> dict[str, Any]:
    data = dict(span.get("span_data") or {})
    span_type = str(data.get("type") or "span")
    normalized = {
        "type": span_type,
        "name": data.get("name") or span_type,
        "input": data.get("input") or {},
        "output": data.get("output") or {},
    }
    if span_type == "function":
        normalized["type"] = "tool_call"
        normalized["name"] = data.get("name") or "function"
        normalized["input"] = data.get("input") or {}
        normalized["output"] = data.get("output") or {}
    return normalized
