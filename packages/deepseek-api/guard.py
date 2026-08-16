"""Integration helper for application-owned DeepSeek tool-calling loops."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from dpi.adapters import normalize
from dpi.model import Decision
from dpi.policy import evaluate


def evaluate_tool_call(tool_call: dict[str, Any]) -> Decision:
    return evaluate(normalize("deepseek-api", json.dumps(tool_call)))


def authorize_tool_call(
    tool_call: dict[str, Any],
    request_approval: Callable[[Decision], bool] | None = None,
) -> Decision:
    decision = evaluate_tool_call(tool_call)
    if decision.effect == "deny":
        raise PermissionError(decision.message)
    if decision.effect == "require_approval":
        if request_approval is None or not request_approval(decision):
            raise PermissionError(decision.message)
    return decision
