#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


plugin_root = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(plugin_root / "runtime"))


def deny_runtime_failure(detail: str) -> int:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Defensive prompt-injection could not load its local policy runtime; "
                f"the operation was denied safely ({detail})."
            ),
        }
    }
    print(json.dumps(output, separators=(",", ":")))
    return 0


def main() -> int:
    try:
        from dpi.adapters import AdapterInputError, invalid_action, normalize, render_context, render_native
        from dpi.policy import evaluate
    except Exception as exc:
        if len(sys.argv) > 1 and sys.argv[1] == "pre":
            return deny_runtime_failure(type(exc).__name__)
        return 0

    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "pre":
        raw = sys.stdin.read()
        try:
            action = normalize("codex", raw)
        except AdapterInputError:
            action = invalid_action("codex")
        output = render_native("codex", evaluate(action))
    elif mode == "context" and len(sys.argv) > 2:
        output = render_context("codex", sys.argv[2])
    else:
        return 0

    if output is not None:
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
