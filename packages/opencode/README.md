# OpenCode adapter

Install the `dpi` command with `python3 -m pip install .`, then load
`defensive-prompt-injection.ts` as an OpenCode V2 plugin.

OpenCode currently exposes a blocking `execute.before` hook but no portable
force-approval result. The adapter therefore throws on both `require_approval`
and `deny`. Treat this adapter as experimental while the V2 plugin API is beta.
