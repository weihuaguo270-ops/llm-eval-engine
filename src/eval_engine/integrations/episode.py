"""Framework-neutral evaluation episode import and deterministic verification."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


EPISODE_SCHEMA_VERSION = "evaluation-episode/v1"
SUPPORTED_SPLITS = {"dev", "golden", "held_out", "production"}


@dataclass
class EvaluationEpisode:
    """One task run with enough evidence for replay and release comparison."""

    episode_id: str
    task: str
    trajectory: dict[str, Any]
    framework: str = "format_b"
    agent_version: str = ""
    split: str = "dev"
    acceptance_criteria: list[str] = field(default_factory=list)
    expected_state: dict[str, Any] = field(default_factory=dict)
    final_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EPISODE_SCHEMA_VERSION,
            "episode_id": self.episode_id,
            "task": self.task,
            "framework": self.framework,
            "agent_version": self.agent_version,
            "split": self.split,
            "acceptance_criteria": list(self.acceptance_criteria),
            "expected_state": copy.deepcopy(self.expected_state),
            "final_state": copy.deepcopy(self.final_state),
            "trajectory": copy.deepcopy(self.trajectory),
            "metadata": copy.deepcopy(self.metadata),
        }


@dataclass(frozen=True)
class StateCheck:
    path: str
    expected: Any
    actual: Any
    passed: bool


@dataclass
class EpisodeVerification:
    episode_id: str
    passed: bool
    checks: list[StateCheck]
    missing_expected_state: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "passed": self.passed,
            "missing_expected_state": self.missing_expected_state,
            "checks": [
                {
                    "path": check.path,
                    "expected": check.expected,
                    "actual": check.actual,
                    "passed": check.passed,
                }
                for check in self.checks
            ],
        }


def import_episode(payload: Mapping[str, Any], *, framework: str = "auto") -> EvaluationEpisode:
    """Normalize an EvaluationEpisode, Format B trace, or supported SDK trace."""
    source = dict(payload)
    if source.get("schema_version") == EPISODE_SCHEMA_VERSION:
        return _episode_from_envelope(source)

    detected = _detect_framework(source) if framework == "auto" else framework
    if detected == "format_b":
        trajectory = _normalize_format_b(source)
    elif detected == "langgraph":
        trajectory = _langgraph_to_format_b(source)
    elif detected == "openai_agents":
        trajectory = _openai_agents_to_format_b(source)
    else:
        raise ValueError(f"unsupported episode framework: {detected}")

    episode_id = str(
        source.get("episode_id")
        or source.get("run_id")
        or source.get("trace_id")
        or trajectory.get("session_id")
        or ""
    )
    if not episode_id:
        raise ValueError("episode_id, run_id, trace_id, or session_id is required")
    split = str(source.get("split") or "dev")
    _validate_split(split)
    return EvaluationEpisode(
        episode_id=episode_id,
        task=str(source.get("task") or trajectory.get("query") or ""),
        trajectory=trajectory,
        framework=detected,
        agent_version=str(source.get("agent_version") or ""),
        split=split,
        acceptance_criteria=list(source.get("acceptance_criteria") or []),
        expected_state=dict(source.get("expected_state") or {}),
        final_state=dict(source.get("final_state") or {}),
        metadata=dict(source.get("metadata") or {}),
    )


def verify_episode_state(episode: EvaluationEpisode) -> EpisodeVerification:
    """Require every expected leaf value to exist in the final business state."""
    if not episode.expected_state:
        return EpisodeVerification(
            episode_id=episode.episode_id,
            passed=False,
            checks=[],
            missing_expected_state=True,
        )
    checks: list[StateCheck] = []
    _compare_expected_subset(
        episode.expected_state,
        episode.final_state,
        path="$",
        checks=checks,
    )
    return EpisodeVerification(
        episode_id=episode.episode_id,
        passed=bool(checks) and all(check.passed for check in checks),
        checks=checks,
    )


def _episode_from_envelope(source: dict[str, Any]) -> EvaluationEpisode:
    required = ("episode_id", "task", "trajectory")
    missing = [name for name in required if name not in source]
    if missing:
        raise ValueError(f"episode missing required fields: {', '.join(missing)}")
    split = str(source.get("split") or "dev")
    _validate_split(split)
    return EvaluationEpisode(
        episode_id=str(source["episode_id"]),
        task=str(source["task"]),
        trajectory=_normalize_format_b(dict(source["trajectory"])),
        framework=str(source.get("framework") or "format_b"),
        agent_version=str(source.get("agent_version") or ""),
        split=split,
        acceptance_criteria=list(source.get("acceptance_criteria") or []),
        expected_state=dict(source.get("expected_state") or {}),
        final_state=dict(source.get("final_state") or {}),
        metadata=dict(source.get("metadata") or {}),
    )


def _detect_framework(source: Mapping[str, Any]) -> str:
    if isinstance(source.get("steps"), list) and "session_id" in source:
        return "format_b"
    if isinstance(source.get("nodes"), list) or isinstance(source.get("events"), list):
        return "langgraph"
    if isinstance(source.get("spans"), list):
        return "openai_agents"
    raise ValueError("cannot detect trajectory framework")


def _normalize_format_b(source: dict[str, Any]) -> dict[str, Any]:
    steps = source.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Format B trajectory requires non-empty steps")
    normalized = copy.deepcopy(source)
    for index, step in enumerate(normalized["steps"], start=1):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{index - 1}] must be an object")
        step.setdefault("step", index)
    normalized.setdefault("query", "")
    normalized.setdefault("final_answer", "")
    normalized.setdefault("session_id", "external-format-b")
    return normalized


def _langgraph_to_format_b(source: dict[str, Any]) -> dict[str, Any]:
    records = source.get("nodes") or source.get("events") or []
    steps = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            continue
        tool = record.get("tool") or record.get("tool_name")
        step: dict[str, Any] = {
            "step": index,
            "thought": str(
                record.get("thought")
                or record.get("planner_text")
                or record.get("node_name")
                or ""
            ),
            "observation": str(record.get("output") or record.get("tool_result") or ""),
        }
        if tool:
            step["action"] = {
                "name": str(tool),
                "arguments": _arguments_json(
                    record.get("arguments") or record.get("tool_payload") or {}
                ),
            }
        steps.append(step)
    return _normalize_format_b(
        {
            "session_id": str(source.get("run_id") or source.get("episode_id") or "langgraph"),
            "query": _text_value(source.get("input") or source.get("inputs")),
            "model": str(source.get("model") or ""),
            "steps": steps,
            "final_answer": _text_value(source.get("output") or source.get("outputs")),
        }
    )


def _openai_agents_to_format_b(source: dict[str, Any]) -> dict[str, Any]:
    steps = []
    for index, span in enumerate(source.get("spans") or [], start=1):
        if not isinstance(span, Mapping):
            continue
        span_type = str(span.get("type") or span.get("span_type") or "")
        tool = span.get("tool_name") or span.get("name") if "tool" in span_type else None
        step: dict[str, Any] = {
            "step": index,
            "thought": str(span.get("reasoning") or span.get("name") or span_type),
            "observation": _text_value(span.get("output") or span.get("result")),
        }
        if tool:
            step["action"] = {
                "name": str(tool),
                "arguments": _arguments_json(span.get("input") or span.get("arguments") or {}),
            }
        steps.append(step)
    return _normalize_format_b(
        {
            "session_id": str(source.get("trace_id") or source.get("episode_id") or "openai"),
            "query": _text_value(source.get("input")),
            "model": str(source.get("model") or ""),
            "steps": steps,
            "final_answer": _text_value(source.get("output")),
        }
    )


def _arguments_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _validate_split(split: str) -> None:
    if split not in SUPPORTED_SPLITS:
        raise ValueError(f"unsupported split: {split}")


def _compare_expected_subset(
    expected: Any,
    actual: Any,
    *,
    path: str,
    checks: list[StateCheck],
) -> None:
    if isinstance(expected, Mapping):
        actual_mapping = actual if isinstance(actual, Mapping) else {}
        for key, value in expected.items():
            child_path = f"{path}.{key}"
            _compare_expected_subset(
                value,
                actual_mapping.get(key),
                path=child_path,
                checks=checks,
            )
        return
    checks.append(
        StateCheck(path=path, expected=expected, actual=actual, passed=actual == expected)
    )
