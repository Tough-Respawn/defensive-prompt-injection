from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from dpi.adapters import (  # noqa: E402
    AdapterInputError,
    invalid_action,
    normalize,
    render_context,
    render_native,
)
from dpi.policy import evaluate  # noqa: E402


class NormalizationTests(unittest.TestCase):
    def test_claude_and_codex_share_the_canonical_shape(self) -> None:
        raw = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
        claude = normalize("claude", raw)
        codex = normalize("codex", raw)
        self.assertEqual(claude.kind, "process.exec")
        self.assertEqual(codex.kind, "process.exec")
        self.assertEqual(claude.arguments, codex.arguments)

    def test_codewhale_uses_the_historical_deepseek_environment(self) -> None:
        action = normalize(
            "deepseek-tui",
            "",
            env={
                "DEEPSEEK_TOOL_NAME": "exec_shell",
                "DEEPSEEK_TOOL_ARGS": json.dumps({"command": "git status"}),
            },
        )
        self.assertEqual(action.harness, "codewhale")
        self.assertEqual(action.kind, "process.exec")

    def test_codewhale_rejects_a_possibly_truncated_argument_preview(self) -> None:
        with self.assertRaises(AdapterInputError):
            normalize(
                "codewhale",
                "",
                env={
                    "DEEPSEEK_TOOL_NAME": "write_file",
                    "DEEPSEEK_TOOL_ARGS": "x" * 10_000,
                },
            )

    def test_deepseek_api_function_arguments_are_decoded(self) -> None:
        action = normalize(
            "deepseek-api",
            json.dumps(
                {
                    "function": {
                        "name": "send_message",
                        "arguments": json.dumps({"to": "outside@example.test"}),
                    }
                }
            ),
        )
        self.assertEqual(action.kind, "function.call")
        self.assertEqual(action.arguments["to"], "outside@example.test")

    def test_official_deepseek_harness_has_a_distinct_adapter(self) -> None:
        action = normalize(
            "dsh",
            json.dumps(
                {
                    "tool_name": "bash",
                    "arguments": {"command": "git status"},
                }
            ),
        )
        self.assertEqual(action.harness, "deepseek-harness")
        self.assertEqual(action.kind, "process.exec")

    def test_bare_deepseek_name_is_rejected_as_ambiguous(self) -> None:
        with self.assertRaises(AdapterInputError):
            normalize("deepseek", json.dumps({"name": "bash", "arguments": {}}))

    def test_invalid_json_is_rejected_by_the_adapter(self) -> None:
        with self.assertRaises(AdapterInputError):
            normalize("codex", "{")

    def test_invalid_canonical_kind_is_rejected(self) -> None:
        with self.assertRaises(AdapterInputError):
            normalize(
                "canonical",
                json.dumps({"tool_name": "x", "kind": "made.up", "arguments": {}}),
            )


class PolicyTests(unittest.TestCase):
    def decision(self, harness: str, payload: dict[str, object]):
        return evaluate(normalize(harness, json.dumps(payload)))

    def test_ordinary_read_is_allowed(self) -> None:
        decision = self.decision(
            "claude",
            {"tool_name": "Read", "tool_input": {"file_path": "/work/src/app.py"}},
        )
        self.assertEqual(decision.effect, "allow")

    def test_sensitive_path_requires_approval(self) -> None:
        decision = self.decision(
            "claude",
            {
                "tool_name": "Read",
                "tool_input": {"file_path": "/home/alice/.ssh/id_ed25519"},
            },
        )
        self.assertEqual(decision.effect, "require_approval")
        self.assertEqual(decision.category, "sensitive-local-data")

    def test_protected_persistence_requires_approval(self) -> None:
        decision = self.decision(
            "codex",
            {
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Update File: .codex/config.toml\n"
                },
            },
        )
        self.assertEqual(decision.effect, "require_approval")
        self.assertEqual(decision.category, "persistent-security-configuration")

    def test_instruction_filename_in_benign_content_does_not_change_target(self) -> None:
        decision = self.decision(
            "claude",
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/work/README.md",
                    "content": "See AGENTS.md for repository conventions.",
                },
            },
        )
        self.assertEqual(decision.effect, "allow")

    def test_network_shell_requires_approval(self) -> None:
        decision = self.decision(
            "codewhale",
            {"tool_name": "exec_shell", "tool_input": {"command": "curl https://outside.test"}},
        )
        self.assertEqual(decision.rule_id, "external-network-command")

    def test_mcp_server_name_does_not_create_a_false_mutation(self) -> None:
        decision = self.decision(
            "codex",
            {"tool_name": "mcp__sendgrid__get_message", "tool_input": {"id": "123"}},
        )
        self.assertEqual(decision.effect, "allow")

    def test_camel_case_mcp_mutation_requires_approval(self) -> None:
        decision = self.decision(
            "codex",
            {
                "tool_name": "mcp__mail__sendMessage",
                "tool_input": {"to": "outside@example.test"},
            },
        )
        self.assertEqual(decision.rule_id, "mutating-mcp-tool")

    def test_deepseek_generic_mutation_requires_approval(self) -> None:
        decision = evaluate(
            normalize(
                "deepseek-api",
                json.dumps(
                    {
                        "function": {
                            "name": "send_message",
                            "arguments": json.dumps({"to": "outside@example.test"}),
                        }
                    }
                ),
            )
        )
        self.assertEqual(decision.effect, "require_approval")

    def test_invalid_action_is_denied(self) -> None:
        self.assertEqual(evaluate(invalid_action("codex")).effect, "deny")


class NativeDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        action = normalize(
            "claude",
            json.dumps(
                {"tool_name": "Read", "tool_input": {"file_path": "/home/a/.aws/credentials"}}
            ),
        )
        self.decision = evaluate(action)

    def test_claude_can_force_an_approval_prompt(self) -> None:
        output = render_native("claude", self.decision)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_codex_falls_back_to_deny(self) -> None:
        output = render_native("codex", self.decision)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_codewhale_falls_back_to_deny(self) -> None:
        self.assertEqual(render_native("codewhale", self.decision)["decision"], "deny")

    def test_codewhale_ask_is_explicit_opt_in(self) -> None:
        output = render_native("codewhale", self.decision, codewhale_approval="ask")
        self.assertEqual(output["decision"], "ask")

    def test_deepseek_harness_uses_its_native_ask_decision(self) -> None:
        output = render_native("deepseek-harness", self.decision)
        self.assertEqual(output["kind"], "ask")

    def test_context_uses_the_native_event_name(self) -> None:
        output = render_context("codex", "session-start")
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")


class PackageContractTests(unittest.TestCase):
    def test_json_and_toml_package_manifests_parse(self) -> None:
        for path in [
            ROOT / "harnesses.json",
            ROOT / "schemas" / "action.schema.json",
            ROOT / "schemas" / "decision.schema.json",
            ROOT
            / "packages"
            / "codex"
            / "plugins"
            / "defensive-prompt-injection"
            / ".codex-plugin"
            / "plugin.json",
            ROOT
            / "packages"
            / "codex"
            / "plugins"
            / "defensive-prompt-injection"
            / "hooks"
            / "hooks.json",
            ROOT / "packages" / "deepseek-harness" / "package.json",
        ]:
            self.assertIsInstance(json.loads(path.read_text()), dict)
        self.assertIsInstance(tomllib.loads((ROOT / "packages" / "codewhale" / "hooks.toml").read_text()), dict)

    def test_no_unavailable_approval_silently_allows(self) -> None:
        matrix = json.loads((ROOT / "harnesses.json").read_text())
        for name, harness in matrix["harnesses"].items():
            if harness["can_force_approval"] is not True:
                self.assertEqual(
                    harness["require_approval_fallback"],
                    "deny",
                    f"{name} must fail closed when approval cannot be forced",
                )

    def test_deepseek_harness_approval_is_conditionally_prompted_but_fail_closed(self) -> None:
        matrix = json.loads((ROOT / "harnesses.json").read_text())
        harness = matrix["harnesses"]["deepseek-harness"]
        self.assertEqual(harness["can_force_approval"], "conditional")
        self.assertEqual(harness["require_approval_native_decision"], "ask")
        self.assertEqual(harness["require_approval_fallback"], "deny")

    def test_coverage_matrix_does_not_claim_unshipped_post_hooks(self) -> None:
        matrix = json.loads((ROOT / "harnesses.json").read_text())
        self.assertEqual(matrix["matrix_scope"], "shipped_adapter_coverage")
        for harness_name in ("opencode", "codewhale", "deepseek-harness"):
            self.assertFalse(matrix["harnesses"][harness_name]["post_result"])

    def test_vendored_plugin_runtimes_match_source(self) -> None:
        runtimes = [
            ROOT
            / "packages"
            / "codex"
            / "plugins"
            / "defensive-prompt-injection"
            / "runtime"
            / "dpi",
            ROOT / "packages" / "deepseek-harness" / "runtime" / "dpi",
        ]
        for runtime in runtimes:
            for source in (ROOT / "src" / "dpi").glob("*.py"):
                self.assertEqual(source.read_bytes(), (runtime / source.name).read_bytes())

    def test_codex_plugin_guard_denies_without_ask(self) -> None:
        plugin = (
            ROOT
            / "packages"
            / "codex"
            / "plugins"
            / "defensive-prompt-injection"
        )
        payload = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "curl https://outside.test"}}
        )
        result = subprocess.run(
            [sys.executable, str(plugin / "hooks" / "guard.py"), "pre"],
            input=payload,
            text=True,
            capture_output=True,
            env={**os.environ, "PLUGIN_ROOT": str(plugin)},
            check=True,
        )
        output = json.loads(result.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_codewhale_cli_consumes_the_native_environment(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "dpi", "hook", "codewhale"],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "PYTHONPATH": str(SRC),
                "DEEPSEEK_TOOL_NAME": "exec_shell",
                "DEEPSEEK_TOOL_ARGS": json.dumps({"command": "curl https://outside.test"}),
            },
            cwd=ROOT,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["decision"], "deny")

    def test_deepseek_harness_cli_emits_native_ask(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "read",
                "arguments": {"path": "/home/alice/.dsh/.credentials.yaml"},
            }
        )
        result = subprocess.run(
            [sys.executable, "-m", "dpi", "hook", "deepseek-harness"],
            input=payload,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(SRC)},
            cwd=ROOT,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["kind"], "ask")

    def test_deepseek_harness_plugin_uses_blocking_native_waterfall(self) -> None:
        plugin = ROOT / "packages" / "deepseek-harness"
        source = (plugin / "index.js").read_text()
        patch = (plugin / "cordis.patch.yml").read_text()
        self.assertIn("ctx.on('tools/pre-execute'", source)
        self.assertIn("return next()", source)
        self.assertIn("kind: 'ask'", source)
        self.assertIn("kind: 'deny'", source)
        self.assertIn("{ prepend: true }", source)
        self.assertIn("runtime failed closed", source)
        self.assertIn("name: dsh-defensive-prompt-injection", patch)

    def test_deepseek_helper_fails_closed_without_approval_callback(self) -> None:
        helper_path = ROOT / "packages" / "deepseek-api" / "guard.py"
        spec = importlib.util.spec_from_file_location("dpi_deepseek_guard", helper_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tool_call = {
            "function": {
                "name": "send_message",
                "arguments": json.dumps({"to": "outside@example.test"}),
            }
        }
        with self.assertRaises(PermissionError):
            module.authorize_tool_call(tool_call)
        self.assertEqual(
            module.authorize_tool_call(tool_call, lambda _decision: True).effect,
            "require_approval",
        )

    def test_opencode_adapter_is_fail_closed(self) -> None:
        source = (ROOT / "packages" / "opencode" / "defensive-prompt-injection.ts").read_text()
        self.assertIn('ctx.tool.hook("execute.before"', source)
        self.assertIn("runtime failed closed", source)
        self.assertIn('!== "allow"', source)


if __name__ == "__main__":
    unittest.main()
