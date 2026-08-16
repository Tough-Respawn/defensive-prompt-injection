# DeepSeek Harness adapter

This package is a native Cordis bundle for the official DeepSeek Harness
(`deepseek-ai/deepseek-harness`, command `dsh`). It is separate from the
CodeWhale adapter and from the DeepSeek model API helper.

The plugin prepends itself to the blocking `tools/pre-execute` waterfall.
Ordinary calls delegate with `next()`, high-risk calls return `ask`, and
malformed input or runtime failures return `deny`. In DeepSeek Harness, an
`ask` prompts under the `ask` approval policy; the `never` policy and an absent,
cancelled, rejected, or unavailable approval channel deny the operation.

## Install from this checkout

Python 3.10 or newer must be available as `python3` (`py -3` on Windows). From
the repository root:

```sh
dsh plugin --profile web add ./packages/deepseek-harness
dsh --profile web --dump-config
```

The dump should contain a row named `defensive-prompt-injection`. Start the
profile normally and make a harmless tool call plus a protected test call; the
latter should display a one-shot approval request.

Set `DPI_PYTHON` to an explicit Python executable if the default launcher is
not on `PATH`. The policy runtime is vendored in this bundle and needs no pip
installation.

## Security behavior

- Full parsed tool arguments are evaluated before dispatch.
- A policy crash, timeout, malformed response, protocol mismatch, or child
  process failure denies the call.
- Python runs in isolated, no-site mode against only the vendored policy path;
  ambient `PYTHONPATH` and user-site startup modules cannot replace the engine.
- The policy response must echo the exact tool name and arguments before an
  `allow` is accepted.
- Existing Harness sandbox and approval policies remain active; the plugin
  delegates ordinary calls through the rest of the waterfall.

DeepSeek Harness is currently a developer preview and announces future
compatibility-breaking changes. See `COMPATIBILITY.md` for the pinned native
contract and revalidate it when upgrading `dsh`.
