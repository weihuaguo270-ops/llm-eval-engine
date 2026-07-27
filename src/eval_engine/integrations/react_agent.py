"""react_agent — 与姊妹仓 react-agent 的集成桥接"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

# benchmark profile 名 → react-agent LLM_PROVIDER
PROFILE_PROVIDERS: dict[str, str] = {
    "deepseek-v3": "deepseek",
    "gpt-4o-mini": "openai",
    "qwen-plus": "ollama",
}


@dataclass
class AgentRunResult:
    query: str
    stdout: str
    trajectory: Optional[dict[str, Any]]
    exit_code: int
    duration_ms: int
    provider: str
    mode: str
    error: Optional[str] = None


def default_react_agent_roots() -> list[Path]:
    here = Path(__file__).resolve()
    eval_root = here.parents[3]  # .../llm-eval-engine/
    return [
        eval_root.parent / "react-agent",
        Path(os.environ.get("REACT_AGENT_ROOT", "")),
    ]


def find_react_agent_root(explicit: Optional[str] = None) -> Optional[Path]:
    """定位 react-agent 仓库根目录。"""
    if explicit:
        p = Path(explicit).resolve()
        return p if _is_react_agent_root(p) else None
    for cand in default_react_agent_roots():
        if cand and _is_react_agent_root(cand):
            return cand.resolve()
    return None


def _is_react_agent_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "src" / "react_agent" / "react_loop.py").is_file()
        and (path / "pyproject.toml").is_file()
    )


def ensure_react_agent_importable(root: Path) -> None:
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def has_agent_api_key(provider: str) -> bool:
    mapping = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "ollama": "",  # 本地可无 key
        "custom": "LLM_API_KEY",
    }
    env = mapping.get(provider, "")
    if not env:
        return True
    return bool(os.environ.get(env) or os.environ.get("OPENAI_API_KEY"))


def load_dotenv_from_react_agent(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def run_query_mock_harness(query: str, root: Path) -> AgentRunResult:
    """用 react-agent Harness 录制器生成可 schema 校验的 mock 轨迹（无 LLM）。"""
    ensure_react_agent_importable(root)
    from react_agent.harness import start_trajectory, finish_trajectory
    from react_agent.harness.schema import normalize_trajectory, validate_trajectory

    t = start_trajectory(query, model="benchmark-mock")
    t.add_step(
        1,
        thought=f"Analyze: {query[:80]}",
        action_name="web_search",
        action_args='{"query": "benchmark mock"}',
        observation="mock observation for benchmark",
    )
    t.add_step(2, thought="Compose answer")
    path = finish_trajectory(f"Mock answer for: {query[:120]}")
    traj: dict[str, Any] = {}
    if path and Path(path).is_file():
        traj = json.loads(Path(path).read_text(encoding="utf-8"))
        try:
            Path(path).unlink()
        except OSError:
            pass
    issues = validate_trajectory(traj) if traj else ["empty trajectory"]
    if issues:
        return AgentRunResult(
            query=query,
            stdout="",
            trajectory=None,
            exit_code=1,
            duration_ms=0,
            provider="mock",
            mode="mock",
            error="; ".join(issues),
        )
    traj = normalize_trajectory(traj)
    return AgentRunResult(
        query=query,
        stdout=traj.get("final_answer", ""),
        trajectory=traj,
        exit_code=0,
        duration_ms=50,
        provider="mock",
        mode="mock",
    )


def run_query_via_react_loop(
    query: str,
    root: Path,
    *,
    provider: str = "deepseek",
    timeout: int = 90,
    max_steps: Optional[int] = 8,
) -> AgentRunResult:
    """经 react-agent eval.runner 子进程跑 react_loop 并取 trajectory。"""
    ensure_react_agent_importable(root)
    load_dotenv_from_react_agent(root)
    from react_agent.eval.runner import run_single_case

    stdout, trajectory, exit_code, duration = run_single_case(
        query,
        timeout=timeout,
        provider=provider,
        max_steps=max_steps,
        extra_env={
            "REACT_AGENT_DISABLE_MCP": "1",
            "REACT_AGENT_SKIP_RAG": "1",
            "REACT_AGENT_SANDBOX_PREWARM": "0",
        },
    )
    if trajectory:
        try:
            from react_agent.harness.schema import normalize_trajectory

            trajectory = normalize_trajectory(trajectory)
        except Exception:
            pass
    return AgentRunResult(
        query=query,
        stdout=stdout or "",
        trajectory=trajectory,
        exit_code=exit_code,
        duration_ms=int(float(duration or 0) * 1000),
        provider=provider,
        mode="agent",
        error=None if trajectory else "no trajectory file captured",
    )


def provider_for_profile(profile: str) -> str:
    return PROFILE_PROVIDERS.get(profile, profile)


def run_benchmark_query(
    query: str,
    profile: str,
    *,
    mode: str,
    react_root: Path,
    timeout: int = 90,
    max_steps: Optional[int] = 8,
    frozen_trajectory: Optional[dict] = None,
) -> AgentRunResult:
    """按 mode 跑单条 benchmark query。"""
    if mode == "frozen" and frozen_trajectory:
        return AgentRunResult(
            query=query,
            stdout=frozen_trajectory.get("final_answer", ""),
            trajectory=frozen_trajectory,
            exit_code=0,
            duration_ms=0,
            provider=profile,
            mode="frozen",
        )
    if mode == "mock":
        return run_query_mock_harness(query, react_root)
    if mode == "agent":
        provider = provider_for_profile(profile)
        if not has_agent_api_key(provider):
            return AgentRunResult(
                query=query,
                stdout="",
                trajectory=None,
                exit_code=2,
                duration_ms=0,
                provider=provider,
                mode="agent",
                error=f"missing API key for provider={provider}",
            )
        return run_query_via_react_loop(
            query, react_root, provider=provider, timeout=timeout, max_steps=max_steps,
        )
    raise ValueError(f"unknown mode: {mode}")
