# Claude Code Hook + Plugin Schema Findings

**Date:** 2026-05-13
**Purpose:** Verify the current Claude Code plugin manifest and `PostToolUse` hook
contract before writing Tasks 3 (manifest), 4 (Unix hook), and 5 (Windows hook).
The spec was drafted from prior knowledge; this doc records what the live docs
actually say so we don't bake wrong key names into the implementation.

## Sources

- Plugins overview: https://code.claude.com/docs/en/plugins
- Plugins reference: https://code.claude.com/docs/en/plugins-reference
- Hooks reference: https://code.claude.com/docs/en/hooks

(Both `docs.claude.com/en/docs/claude-code/*` URLs 301-redirect to
`code.claude.com/docs/en/*` — the new canonical home.)

---

## 1. Plugin manifest schema (`.claude-plugin/plugin.json`)

Required fields:

- `name` — string. Unique identifier; also the skill namespace
  (`/<name>:<skill>`).

Optional fields used by this plugin:

- `description` — string. Shown in the plugin manager.
- `version` — string. Recommended (otherwise the git commit SHA is used).
- `author` — object `{ "name": "..." }`.
- `homepage`, `repository`, `license`, `keywords` — strings / arrays.
- `skills`, `commands`, `agents` — string (directory) or array of paths. Default
  locations (`skills/`, `commands/`, `agents/` at plugin root) are auto-discovered
  if these keys are omitted.
- `hooks` — **either an inline object OR a string path to an external JSON file**
  (e.g. `"hooks": "./hooks/hooks.json"`). Default is `hooks/hooks.json` at plugin
  root if the key is omitted.
- `mcpServers`, `lspServers`, `outputStyles`, `dependencies`, `experimental`.

Example (matching what Task 3 will produce):

```json
{
  "name": "defensive-prompt-injection",
  "version": "0.1.0",
  "description": "Defense-in-depth against prompt injection from ingested content",
  "author": { "name": "..." },
  "license": "MIT"
}
```

Note: `skills`, `agents`, `hooks` can be omitted because the auto-discovered
default directories (`skills/`, `agents/`, `hooks/hooks.json`) cover our layout.

---

## 2. Hook configuration shape

**Location:** `hooks/hooks.json` at plugin root (preferred), OR inline under a
top-level `"hooks"` key in `plugin.json`. Both forms use the **same inner
schema** as user-level `~/.claude/settings.json` hooks.

**Exact event name:** `PostToolUse` (PascalCase). Other tool events spelled the
same way: `PreToolUse`, `PostToolBatch`, etc.

**Exact shape (from the official `format-code.sh` reference example):**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|WebFetch|WebSearch|mcp__.*",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}\"/hooks/post-tool-use.sh"
          }
        ]
      }
    ]
  }
}
```

Keys to note:

- Outer event key: `"PostToolUse"` (case-sensitive).
- Each entry is `{ "matcher": "<regex-or-name>", "hooks": [ { ... } ] }` — there
  is a nested `"hooks"` array inside each matcher entry.
- Each handler object has `"type"` (here `"command"`) and `"command"` (string).
  Optional handler keys: `args`, `timeout`, `statusMessage`, `async`, `shell`
  (`"bash"` default, `"powershell"` available), `if`.

**Matcher format:**

- Plain names or pipe lists (`"Bash"`, `"Edit|Write"`) are matched as exact
  strings.
- Anything containing other characters (e.g. `^`, `.`, `*`) is parsed as a
  JavaScript regex. So both `"Read|WebFetch|WebSearch|mcp__.*"` and the spec's
  `"^(Read|WebFetch|WebSearch|mcp__.*)$"` are valid regex forms.
- `"*"`, `""`, or omitted = match all.

**Plugin path token:** `${CLAUDE_PLUGIN_ROOT}` expands to the plugin's install
directory. Use it in `command` strings. Wrap in `"..."` for shell-form
(default) to handle spaces. `${CLAUDE_PLUGIN_DATA}` (persistent state) and
`${CLAUDE_PROJECT_DIR}` (project root) are also available.

---

## 3. PostToolUse stdin payload

A hook receives one JSON object on stdin. Common fields on every event:

```json
{
  "session_id": "abc123",
  "transcript_path": "/home/user/.claude/projects/.../transcript.jsonl",
  "cwd": "/home/user/my-project",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse"
}
```

Tool-event-specific fields (PreToolUse / PostToolUse):

```json
{
  "tool_name": "Read",
  "tool_input":  { "file_path": "/abs/path.md" },
  "tool_use_id": "tool_use_123",
  "tool_response": { ... }    // PostToolUse only — tool result
}
```

All keys are **snake_case**: `tool_name`, `tool_input`, `tool_use_id`,
`tool_response`, `hook_event_name` — NOT camelCase.

(Source: https://code.claude.com/docs/en/hooks)

---

## 4. PostToolUse stdout — additionalContext injection

To inject text back into the agent's context (Layer 1's job), exit `0` and write
this exact JSON to stdout:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "<system-reminder>...</system-reminder>"
  }
}
```

Key spellings are **camelCase** for output (note the contrast with snake_case
input): `hookSpecificOutput`, `hookEventName`, `additionalContext`.

Other universal output fields available alongside `hookSpecificOutput`:
`continue` (bool), `stopReason` (string), `suppressOutput` (bool),
`systemMessage` (string).

## 5. Exit code conventions

- `0` — success. Stdout is parsed as JSON (or treated as plain context text for
  `SessionStart` / `UserPromptSubmit`).
- `2` — **blocking error**. stderr is shown to Claude and the action is
  blocked. This is the only exit code that blocks.
- Any other non-zero — non-blocking error. stderr appears in the transcript;
  the action proceeds.

For Layer 1 we want `0` + JSON stdout (inject reminder, do not block).

---

## 6. Divergences from the spec (`§7.1` and `§4`)

The spec's draft `plugin.json` (lines 341-360) uses two patterns that the live
docs do **not** support. Both must be corrected in Task 3.

### 6.1 OS-conditional `command` object — NOT supported

Spec assumes:

```json
"command": {
  "windows": "hooks/post-tool-use.ps1",
  "unix": "hooks/post-tool-use.sh"
}
```

The docs are explicit: `command` is a **single string** (or string + `args`
array). There is no `{ windows, unix }` form.

**Correct approach.** Use the per-handler `shell` field (`"bash"` or
`"powershell"`) and register **two separate handler entries** under the same
matcher, OR use one shell wrapper that detects the OS. Cleanest pattern for
this plugin:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|WebFetch|WebSearch|mcp__.*",
        "hooks": [
          {
            "type": "command",
            "shell": "bash",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/post-tool-use.sh\""
          },
          {
            "type": "command",
            "shell": "powershell",
            "command": "& \"${CLAUDE_PLUGIN_ROOT}/hooks/post-tool-use.ps1\""
          }
        ]
      }
    ]
  }
}
```

Open question for Task 3/4/5: confirm whether both handlers fire on every
platform (likely yes — `shell` only picks the interpreter, it does not gate by
OS), in which case we need OS detection **inside** each script (early-exit if
wrong platform) OR a single cross-platform wrapper (e.g. a Node/Python
one-liner) instead of two handlers. Safer path: ship one script that no-ops on
the wrong OS, registered once.

### 6.2 Hooks inline in `plugin.json` vs `hooks/hooks.json`

The spec puts the `"hooks"` block inline in `plugin.json`. The docs allow
this, but the **recommended** layout (and what `claude plugin validate`
expects by default) is `hooks/hooks.json` at the plugin root with the same
inner schema. The repo already has a `hooks/` directory (per `§3.1`), so
Task 3 should put the hook config in `hooks/hooks.json` and omit the `hooks`
key from `plugin.json`.

### 6.3 `additionalContext` key — spec is correct, but qualify the path

Spec §4.2 says "a JSON payload whose `additionalContext` field is appended" —
correct key name, but the **full path is `hookSpecificOutput.additionalContext`,
not top-level `additionalContext`**. Tasks 4/5 must emit the nested form:

```json
{ "hookSpecificOutput": { "hookEventName": "PostToolUse", "additionalContext": "..." } }
```

A top-level `{"additionalContext": "..."}` will be silently ignored.

### 6.4 `PostToolUse` event name — spec is correct

PascalCase `PostToolUse` is the documented spelling. No change needed.

### 6.5 Matcher regex — spec is correct

`^(Read|WebFetch|WebSearch|mcp__.*)$` is a valid JS regex matcher. The simpler
form `Read|WebFetch|WebSearch|mcp__.*` (anchorless) is equivalent in practice
since matchers match against the whole tool name. Either works.

---

## 7. Implications for Tasks 3 / 4 / 5

- **Task 3 (manifest):** put hook config in `hooks/hooks.json`, not inline.
  `plugin.json` stays minimal (name/version/description/author/license).
- **Task 3 (hooks.json):** register handlers with `shell: bash` and
  `shell: powershell`, both pointing at `${CLAUDE_PLUGIN_ROOT}/hooks/...`.
  Or register a single platform-neutral wrapper.
- **Task 4 (`post-tool-use.sh`):** read JSON from stdin (`jq -r '.tool_name'`),
  emit JSON to stdout with the **nested** `hookSpecificOutput.additionalContext`
  shape, exit `0`.
- **Task 5 (`post-tool-use.ps1`):** same contract, PowerShell-native JSON
  (`$input | ConvertFrom-Json`, `ConvertTo-Json -Depth 4`). Must emit the same
  nested output shape.
- **Both scripts:** if registered as two handlers (one per `shell`), each
  should no-op cleanly when run on the wrong OS rather than erroring.
