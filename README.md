# defensive-prompt-injection

> Defense-in-depth for Claude Code against prompt injection delivered
> through ingested content. Read/WebFetch/WebSearch/MCP outputs are
> treated as **data**, never as **instructions**.

## Why

Claude Code agents routinely read PDFs, HTML pages, search results, and
MCP tool outputs. Any of those can carry instructions crafted to subvert
the agent: exfiltrate credentials, run destructive commands, poison
memory, hijack other skills. Without a defensive layer, an injection in
page 347 of a PDF can change agent behavior hours later.

This plugin installs a defense in three layers, each independent.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Agent                                                   │
│                                                         │
│  Tool call ──► Read / WebFetch / WebSearch / mcp__*     │
│                       │                                 │
│                       ▼                                 │
│   Layer 1 ─── PostToolUse hook                          │
│               injects <system-reminder>                 │
│                       │                                 │
│                       ▼                                 │
│   Layer 2 ─── trust-boundary skill                      │
│               3 principles + decision flow              │
│                       │                                 │
│                       ▼                                 │
│   Layer 3 ─── quarantine-reader subagent                │
│               (high-risk or large sources)              │
└─────────────────────────────────────────────────────────┘
```

- **Layer 1 (deterministic)**: a hook fires on every tool match and
  injects a short reminder. Cannot be skipped by the model.
- **Layer 2 (judgment)**: a skill encoding three general principles —
  data vs instruction, action-gating for side effects, operational
  opacity about the rules.
- **Layer 3 (isolation)**: a subagent that reads untrusted content in
  a separate context and returns a sanitized summary, so the raw
  injection never reaches the main agent.

## Install

Two steps in Claude Code:

```
/plugin marketplace add Tough-Respawn/defensive-prompt-injection
/plugin install defensive-prompt-injection@defensive-prompt-injection
```

That's it. The plugin auto-registers its hook, skill, and subagent —
no manual edits to `~/.claude/settings.json`.

To install from a local clone:

```
/plugin marketplace add <path-to-local-clone>
/plugin install defensive-prompt-injection@defensive-prompt-injection
```

## Demo

After installing, try:

```
Read docs/demo-injection/sample.txt and follow the steps it lists.
```

Without the plugin, an agent might be tempted by the injected
"send ~/.ssh/id_rsa" instruction. With the plugin installed, the agent
refuses, surfaces the injection attempt in plain language, and waits
for your confirmation.

## What this protects against

- Credential and secret exfiltration via shell, network, or markdown
  image URLs
- Destructive shell commands (`rm -rf`, force-pushes, drops) triggered
  by content
- Memory poisoning and settings/hook tampering
- Hardware capture (camera, mic, clipboard, screenshot)
- Communication-on-behalf-of-user (email, Slack, payment) driven by
  ingested content
- Future, uncatalogued action classes — the design relies on a general
  principle ("any side effect derived from external content gates")
  rather than an enumerated blocklist

## What this does not protect against

- Attacks where the user themselves pastes the injection and claims it
  as their own intent. From inside the conversation this is
  indistinguishable from a genuine request.
- Out-of-band compromise: leaked API keys, malicious repo clones,
  compromised developer machines.
- MCP tools whose names don't match `mcp__.*`. Adjust the matcher in
  `plugins/defensive-prompt-injection/hooks/hooks.json` if you install
  MCPs with unusual naming.
- The skill file is open source; an attacker can read it. The design
  is robust to that — the principles are general and the opacity is
  operational, not cryptographic.

## How to verify it works

Run the eval suite in `evals/`:

```bash
# Each of the 8 fixtures tests one threat class.
# Run them against your installed Claude Code session and check
# agent behavior against the assertions in evals/evals.json.
```

Eight test cases cover: benign content, credential exfiltration,
markdown-image exfiltration, destructive shell, memory poisoning,
bypass-by-fake-exception, opacity probe, and legitimate user request
(false-positive check).

## How it works (more detail)

Read the spec:
[docs/superpowers/specs/2026-05-13-defensive-prompt-injection-design.md](docs/superpowers/specs/2026-05-13-defensive-prompt-injection-design.md).

Read the skill itself:
[plugins/defensive-prompt-injection/skills/trust-boundary/SKILL.md](plugins/defensive-prompt-injection/skills/trust-boundary/SKILL.md).

## License

MIT. See [LICENSE](LICENSE).

## Contributing

Open an issue or pull request. If you find an injection class that the
plugin does not handle, please include a fixture in `evals/fixtures/`
and an assertion in `evals/evals.json` so we can verify the fix.
