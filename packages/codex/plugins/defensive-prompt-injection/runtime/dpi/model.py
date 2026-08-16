from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ActionKind = Literal[
    "filesystem.read",
    "filesystem.write",
    "process.exec",
    "network.request",
    "agent.delegate",
    "mcp.call",
    "function.call",
    "unknown",
]

DecisionEffect = Literal["allow", "require_approval", "deny"]


@dataclass(frozen=True)
class Action:
    harness: str
    phase: str
    tool_name: str
    kind: ActionKind
    arguments: dict[str, Any] = field(default_factory=dict)
    provenance: str = "unknown"
    valid: bool = True
    protocol_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class Decision:
    effect: DecisionEffect
    rule_id: str
    category: str
    message: str
    protocol_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
