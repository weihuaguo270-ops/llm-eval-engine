"""react-agent 集成测试（需姊妹仓 ../react-agent）"""

from pathlib import Path

import pytest

from eval_engine.integrations.react_agent import (
    find_react_agent_root,
    provider_for_profile,
    run_benchmark_query,
)


@pytest.fixture
def react_root():
    root = find_react_agent_root()
    if root is None:
        pytest.skip("react-agent not found at ../react-agent")
    return root


def test_find_react_agent_sibling(react_root: Path):
    assert (react_root / "src" / "react_agent" / "react_loop.py").is_file()
    print(f"[PASS] react-agent at {react_root}")


def test_provider_map():
    assert provider_for_profile("deepseek-v3") == "deepseek"
    assert provider_for_profile("gpt-4o-mini") == "openai"


def test_mock_harness_run(react_root: Path):
    res = run_benchmark_query(
        "计算 1+1",
        "deepseek-v3",
        mode="mock",
        react_root=react_root,
    )
    assert res.trajectory is not None
    assert res.exit_code == 0
    assert res.trajectory.get("steps")
    print(f"[PASS] mock harness steps={len(res.trajectory['steps'])}")
