# Harness support

The shared policy engine classifies canonical actions. Each adapter is
responsible for normalizing native tool calls and translating the result back
without weakening it.

## Decision contract

- `allow`: emit no blocking native decision; normal harness permissions remain.
- `require_approval`: request approval only when the native API guarantees it.
  Otherwise deny the operation.
- `deny`: stop the operation regardless of the harness permission mode when the
  native hook API can enforce that result.

The machine-readable matrix is [`../harnesses.json`](../harnesses.json).
Its booleans describe the surfaces implemented by the adapters shipped in this
repository, not every extension point a harness may expose.

| Shipped adapter | Pre-action gate | Native denial | Approval prompt | Post-result context | Prompt/session context | Output filter |
|---|---:|---:|---:|---:|---:|---:|
| Claude Code | yes | yes | yes | yes | yes | yes |
| Codex | yes | yes | no; deny | yes | yes | no |
| OpenCode | yes | yes | no; deny | no | no | no |
| CodeWhale | interactive TUI | yes | opt-in only; otherwise deny | no | no | no |
| DeepSeek Harness | yes | yes | conditional; otherwise deny | no | no | no |
| DeepSeek API | host-owned | host-owned | host-owned | host-owned | host-owned | host-owned |

## Claude Code

Claude Code supports `allow`, `deny`, and `ask` from `PreToolUse`. The existing
native Bash and PowerShell runtime remains the release implementation while the
canonical v0.4 adapter is tested for behavioral parity.

Reference: <https://code.claude.com/docs/en/hooks>

## Codex

Codex can block supported local function tools with `PreToolUse`, but its
current hook contract does not support `permissionDecision: "ask"`. The adapter
therefore converts both `require_approval` and `deny` to a native denial.
Hosted tools may bypass the local function-tool hook path, so this is useful
guardrail coverage rather than a complete enforcement boundary.

Reference: <https://learn.chatgpt.com/codex/hooks>

## OpenCode

The V2 `execute.before` hook can fail an intercepted operation. The adapter
invokes `dpi`, allows only a canonical `allow`, and throws for every other
result or runtime failure. The V2 API is beta.

Only the pre-action gate is installed by the current adapter; no OpenCode
post-result or prompt-context listener is claimed in the coverage matrix.

Reference: <https://opencode.ai/v2/docs/build/plugins>

## CodeWhale / DeepSeek-TUI

DeepSeek-TUI was renamed CodeWhale and is independent from the DeepSeek model
provider. Its `tool_call_before` event supports `allow`, `deny`, and `ask`, but
`ask` does not downgrade Full Access. The shipped configuration consequently
uses the safe `require_approval -> deny` mapping. An explicit opt-in can use
`ask` only when Full Access has been disabled operationally.

This coverage applies only to the interactive TUI. CodeWhale documents that
`codewhale exec`, CLI subcommands, app-server, and ACP do not fire these hooks.
Its `DEEPSEEK_TOOL_ARGS` preview is capped at 10,000 bytes; the adapter denies a
preview at that boundary because it cannot classify a hidden suffix safely.
The shipped `hooks.toml` installs only `tool_call_before`; post-result support
in the native harness is not claimed as adapter coverage.

Reference: <https://github.com/Hmbown/CodeWhale/blob/main/docs/HOOKS.md>

## DeepSeek Harness (`dsh`)

DeepSeek Harness is the official open-source agent harness from DeepSeek AI. It
uses Cordis plugins and is distinct from both CodeWhale and the DeepSeek model
API. The adapter is an installable `dsh.bundle` package that registers on the
blocking `tools/pre-execute` waterfall.

The plugin receives the complete parsed `exec.name` and `exec.arguments` before
dispatch. It calls `next()` only for a canonical `allow`, returns `{ kind:
'ask' }` for `require_approval`, and returns `{ kind: 'deny' }` for a canonical
denial or any adapter/runtime failure. DeepSeek Harness resolves `ask` through
its one-shot approval service; rejection, cancellation, or an unavailable
approval service denies the operation. If the session approval policy is
`never` (including the stock `danger-full-access` preset), `ask` is rejected
automatically rather than silently granted.

The adapter is validated against official repository commit
`47f943859bef60e4160492346772ded9b24f765a` and
the published `@deepseek-ai/dsh@0.1.0-rc.6` / `dsh-tools@0.1.0-rc.6`
packages. DeepSeek labels the Harness a developer preview and explicitly warns
of compatibility-breaking changes, so the pinned contract in
`packages/deepseek-harness/COMPATIBILITY.md` must be revalidated on upgrade.

References:

- <https://github.com/deepseek-ai/deepseek-harness>
- <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-execution-pipeline.md>
- <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.md>

## DeepSeek API

The official DeepSeek API exposes model function calls, not a universal local
tool executor or hook lifecycle. Applications that own the tool loop can pass
each function call through `packages/deepseek-api/guard.py` before dispatch.
The application must supply approval UI; absent that callback, the helper fails
closed.

Reference: <https://api-docs.deepseek.com/guides/tool_calls>

## Unknown harnesses

If a harness cannot expose every sensitive action before execution, an adapter
alone cannot provide deterministic containment. Run it with OS filesystem and
network isolation, remove ambient credentials, and declare the missing hook
surfaces as degraded coverage.
