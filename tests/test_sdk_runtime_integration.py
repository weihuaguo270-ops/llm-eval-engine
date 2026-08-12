import asyncio

import pytest

from eval_engine.integrations import import_episode, verify_episode_state


def test_real_langgraph_runtime_exports_verifiable_episode():
    pytest.importorskip("langgraph")
    from eval_engine.integrations.sdk_runtime import run_langgraph_expense_episode

    payload = run_langgraph_expense_episode()
    episode = import_episode(payload, framework="langgraph")

    assert payload["metadata"]["runtime"] == "langgraph.StateGraph"
    assert [step["action"]["name"] for step in episode.trajectory["steps"]] == [
        "get_claim",
        "approve_claim",
    ]
    assert verify_episode_state(episode).passed is True


def test_real_openai_agents_runtime_exports_tool_span_and_state():
    pytest.importorskip("agents")
    from eval_engine.integrations.sdk_runtime import run_openai_agents_expense_episode

    payload = asyncio.run(run_openai_agents_expense_episode())
    episode = import_episode(payload, framework="openai_agents")

    assert payload["metadata"]["runtime"] == "openai-agents.Runner"
    assert payload["metadata"]["model"] == "deterministic-local-test-model"
    assert any(
        step.get("action", {}).get("name") == "approve_claim"
        for step in episode.trajectory["steps"]
    )
    assert verify_episode_state(episode).passed is True
