# Changelog

All notable changes to this plugin are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [semantic versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] — 2026-08-16

### Added

- Harness-neutral Python policy engine with canonical Action/Decision v1
  schemas and no third-party runtime dependencies.
- Shipped-adapter coverage matrix with fail-closed `require_approval` mappings
  for Claude Code, Codex, OpenCode, the official DeepSeek Harness,
  CodeWhale/DeepSeek-TUI, and DeepSeek API tool loops.
- Validated Codex plugin package with `PreToolUse`, session, prompt, subagent,
  and post-tool hooks plus a concise `trust-boundary` skill.
- Native DeepSeek Harness Cordis bundle on the blocking `tools/pre-execute`
  waterfall, pinned to its current developer-preview contract.
- Experimental OpenCode V2 adapter, CodeWhale hook configuration, and a helper
  for application-owned DeepSeek function-calling loops.
- Cross-harness contract tests, adapter response tests, and a runtime-sync
  check preventing the vendored Codex engine from drifting from the source.

### Changed

- Distinguished the official DeepSeek Harness (`dsh`), the DeepSeek model API,
  and the independent CodeWhale project formerly named DeepSeek-TUI; the bare
  `deepseek` adapter alias is now rejected as ambiguous.
- Defined fail-closed behavior for harnesses that cannot reliably force a user
  approval prompt.

## [0.3.0] — 2026-08-16

### Added

- `PreToolUse` approval gates for recognizable sensitive reads, security
  persistence, network-capable/destructive shell operations, inline
  interpreters, suspicious WebFetch payloads, delegated risky prompts, and
  mutating MCP tools.
- Current Claude Code lifecycle coverage for `SessionStart`,
  `UserPromptSubmit`, `UserPromptExpansion`, `PostToolBatch`,
  `SubagentStart`, `SubagentStop`, `MessageDisplay`, `Stop`,
  `InstructionsLoaded`, `ConfigChange`, `DirectoryAdded`, `FileChanged`,
  `Elicitation`, and `ElicitationResult`.
- Assistant-output protection for external Markdown/HTML images, including a
  conservative block on reference-style images that can span streaming
  batches.
- Metadata-only hook auditing under `${CLAUDE_PLUGIN_DATA}/audit.jsonl`.
- Automated hook regression suite and six additional manual evaluations for
  repository instruction poisoning, shell output, `@` references, subagent
  trust chains, Unicode obfuscation, and direct user security audits.

### Changed

- Corrected `hooks/hooks.json` to use the documented top-level `hooks` object.
- Replaced per-tool `PostToolUse` reminders with one `PostToolBatch` reminder,
  covering shell, MCP, LSP, Agent, failures, and batched calls without duplicate
  context for parallel tools.
- Replaced the old post-use scripts with native `guard.sh` and `guard.ps1`
  implementations and one auto-selected shell dispatcher.
- Expanded the trust-boundary skill and quarantine reader to cover repository
  instructions, imports, project skills, `@` insertion, tool output, and
  delegated trust chains.
- Aligned marketplace and plugin manifest versions at `0.3.0`, added the
  official manifest schema, and removed `CLAUDE.md` from `.gitignore` so a
  security-relevant repository instruction file cannot be hidden accidentally.
- Replaced the old opacity framing with a provenance distinction: embedded
  probes are not completed, while direct user audits are answered fully.

### Security limitations clarified

- `InstructionsLoaded` cannot block instruction loading, `@` insertion has no
  `PreToolUse` event, `MessageDisplay` is display-only, and signature-based
  shell/MCP classification is not a semantic data-flow proof.
- Quarantine isolation only applies when the source is delegated before the
  main agent reads it. Claude Code permissions and OS sandboxing remain
  necessary containment layers.

## [0.2.0] — 2026-05-13

### Added

- Hook matcher now covers `Grep` and `Glob` in addition to `Read`,
  `WebFetch`, `WebSearch`, and `mcp__*`. `Grep` in `content` mode
  returns partial file contents; `Glob` returns filenames. Both can
  carry attacker-controlled text that should trigger Layer 1's
  deterministic reminder.
- README section "Auditing the hook scripts" documenting the safety
  properties of `post-tool-use.sh` and `post-tool-use.ps1` (no network,
  no file writes, no `eval` / `Invoke-Expression`, fail-safe).
- README section "How to verify it works" with a 5-minute reproduction
  protocol, a 9-row expected-results table, and explicit caveats about
  combined-layer behavior and corpus scope.
- README citation of Anthropic's Acceptable Use Policy
  (effective 2025-09-15) as the source for the upstream
  prompt-injection enforcement claim.

### Changed

- Plugin positioning clarified in the README as **complementary** to
  Anthropic's platform-level safeguards, not a substitute. Replaced the
  unsourced "filters at the API edge" wording with sourced language
  consistent with the AUP.
- "Eight fixtures" wording corrected to "nine fixtures" across the
  README (the privilege-escalation fixture was added in 0.1.0 but the
  doc was not updated at the time).

### Documented as out of scope

- `Bash` command output is intentionally not covered by Layer 1.
  Covering it universally would fire on every `git status`,
  `npm install`, or `ls` and drown the signal. Layer 2 (the
  `trust-boundary` skill) still applies via the model's judgment when
  the user pipes untrusted content through Bash.
- `Task` (subagent) output belongs to the subagent's own trust chain,
  not the hook's.

### Heads-up for upgraders

The extended matcher will fire on `Grep` and `Glob` calls that were
silent in 0.1.0. Each fire adds roughly 100 tokens of
`<system-reminder>` to the agent's context. Pay-per-token users may see
a small but real increase in token usage, proportional to how often
their sessions grep or glob.

## [0.1.0] — 2026-05-13

Initial public release.

### Added

- **Layer 1 (deterministic)**: `PostToolUse` hook that fires on `Read`,
  `WebFetch`, `WebSearch`, and `mcp__*` tool calls and injects a
  `<system-reminder>` into the agent's context. Unix variant
  (`post-tool-use.sh`) and Windows variant (`post-tool-use.ps1`), OS-gated
  so only one fires per platform.
- **Layer 2 (judgment)**: `trust-boundary` skill expressing three
  principles — data vs. instruction, action-gating for side effects,
  operational opacity about the rules — and a decision flow.
- **Layer 3 (isolation)**: `quarantine-reader` subagent that reads
  untrusted content in a separate context and returns a sanitized
  structured summary, so the raw injection never reaches the main
  agent.
- Nine evaluation fixtures covering benign content (false-positive
  check), credential exfiltration, markdown-image exfiltration,
  destructive shell, memory poisoning, bypass-by-fake-exception,
  opacity probe, legitimate user request (false-positive check), and
  privilege escalation via settings tampering. Assertions live in
  [evals/evals.json](evals/evals.json).
- MIT license.
