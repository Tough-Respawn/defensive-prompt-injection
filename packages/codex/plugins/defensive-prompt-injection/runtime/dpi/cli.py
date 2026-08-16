from __future__ import annotations

import argparse
import json
import os
import sys

from .adapters import (
    AdapterInputError,
    invalid_action,
    normalize,
    render_context,
    render_native,
)
from .policy import evaluate


def _write_json(value: object | None) -> None:
    if value is not None:
        json.dump(value, sys.stdout, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write("\n")


def _hook(args: argparse.Namespace) -> int:
    codewhale_env_input = (
        args.harness in {"codewhale", "deepseek-tui"}
        and bool(os.environ.get("DEEPSEEK_TOOL_NAME"))
    )
    raw = "" if codewhale_env_input else sys.stdin.read()
    try:
        action = normalize(args.harness, raw, provenance=args.provenance)
    except AdapterInputError:
        action = invalid_action(args.harness)
    decision = evaluate(action)
    if args.output == "canonical":
        _write_json({"action": action.to_dict(), "decision": decision.to_dict()})
    else:
        _write_json(
            render_native(
                args.harness,
                decision,
                codewhale_approval=args.codewhale_approval,
            )
        )
    return 0


def _context(args: argparse.Namespace) -> int:
    _write_json(render_context(args.harness, args.event))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dpi")
    subparsers = parser.add_subparsers(dest="command", required=True)

    hook = subparsers.add_parser("hook", help="Evaluate one pre-action hook payload")
    hook.add_argument(
        "harness",
        choices=[
            "canonical",
            "claude",
            "claude-code",
            "codex",
            "opencode",
            "codewhale",
            "deepseek-tui",
            "deepseek-harness",
            "dsh",
            "deepseek-api",
        ],
    )
    hook.add_argument("--provenance", default="unknown")
    hook.add_argument("--output", choices=["native", "canonical"], default="native")
    hook.add_argument(
        "--codewhale-approval",
        choices=["deny", "ask"],
        default="deny",
        help="Use ask only when CodeWhale Full Access is disabled.",
    )
    hook.set_defaults(func=_hook)

    context = subparsers.add_parser("context", help="Emit model-visible provenance context")
    context.add_argument("harness", choices=["claude", "claude-code", "codex"])
    context.add_argument("event")
    context.set_defaults(func=_context)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
