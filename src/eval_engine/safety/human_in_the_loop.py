"""human_in_the_loop — Human oversight interface for eval-loop decisions

Provides a callback-based interface for human-in-the-loop approval
of tool calls, direction changes, and revision injections.
"""

from __future__ import annotations
from typing import Any, Callable, Optional


class HumanInTheLoop:
    """Human-in-the-loop manager

    Wraps human approval callbacks for various decision points
    in the eval loop and agent execution flow.

    Usage:
        def ask_user(prompt: str, options: list[str]) -> str:
            return input(f"{prompt} {options}: ")

        hitl = HumanInTheLoop(ask_fn=ask_user)
        if hitl.check_tool_call("write_file", {"path": "/etc/passwd"}):
            ...  # proceed
    """

    def __init__(
        self,
        ask_fn: Optional[Callable[[str, list[str]], str]] = None,
        auto_approve: bool = False,
    ):
        """
        Args:
            ask_fn: Callback for user interaction. Receives (prompt, options).
                    Should return the user's chosen option text.
            auto_approve: If True, automatically approves all requests.
                          Only use in non-production / trusted scenarios.
        """
        self._ask_fn = ask_fn
        self._auto_approve = auto_approve
        self._approval_log: list[dict] = []

    def check_tool_call(
        self,
        tool_name: str,
        tool_args: dict,
        reason: str = "",
    ) -> bool:
        """Check if a tool call is approved

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments for the tool call
            reason: Reason for the tool call

        Returns:
            True if approved, False if denied
        """
        if self._auto_approve:
            self._approval_log.append({
                "type": "tool_call",
                "tool": tool_name,
                "approved": True,
                "auto": True,
            })
            return True

        if self._ask_fn is None:
            # No human available: allow by default
            return True

        prompt = f"允许调用 {tool_name}({tool_args})？"
        if reason:
            prompt += f"\n理由：{reason}"

        result = self._ask_fn(prompt, ["允许", "拒绝"])
        approved = result == "允许"

        self._approval_log.append({
            "type": "tool_call",
            "tool": tool_name,
            "approved": approved,
        })
        return approved

    def check_direction(
        self,
        action: str,
        details: str = "",
    ) -> bool:
        """Check if a direction/action change is approved

        Used for revision injection approval and re-execution approval
        in the eval loop.

        Args:
            action: Description of the proposed action
            details: Additional details

        Returns:
            True if approved
        """
        if self._auto_approve:
            return True

        if self._ask_fn is None:
            return True

        prompt = f"{action}"
        if details:
            prompt += f"\n{details}"

        result = self._ask_fn(prompt, ["继续", "停止"])
        return result == "继续"

    @property
    def approval_log(self) -> list[dict]:
        """Get the approval history log"""
        return list(self._approval_log)
