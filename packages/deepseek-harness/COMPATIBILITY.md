# Compatibility contract

Validated against the official `deepseek-ai/deepseek-harness` repository at
commit `47f943859bef60e4160492346772ded9b24f765a` (2026-08-13), plus the
published `@deepseek-ai/dsh@0.1.0-rc.6` and
`@deepseek-ai/dsh-tools@0.1.0-rc.6` packages. The rc.6 CLI installed this
bundle into an isolated Web profile, included its patch in the effective
configuration, and booted the profile successfully.

The adapter relies on these native invariants:

- a function plugin exports `name`, `inject`, and `apply`;
- `inject = ['tools']` waits for the tool registry;
- `tools/pre-execute` is an async Cordis waterfall invoked before tool dispatch;
- `{ prepend: true }` places the security listener before existing listeners;
- an allowing listener calls `next()` so downstream policies still run;
- `{ kind: 'deny', reason }` skips the tool body;
- `{ kind: 'ask', reason? }` dispatches only after `allowed-once`; missing,
  cancelled, rejected, or unavailable approval denies the call;
- the Harness approval policy `never` resolves an ask as `rejected`, not as an
  implicit grant;
- `exec.name`, `exec.arguments`, and `exec.signal` expose the complete parsed
  call and its cancellation signal.

DeepSeek marks the entire Harness as a developer preview. Any change to this
event name, payload, decision vocabulary, waterfall ordering, or approval
fallback must be treated as incompatible until tests and this document are
updated.
