# Changelog

All notable changes to this plugin are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [semantic versioning](https://semver.org/).

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
