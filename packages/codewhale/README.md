# CodeWhale / DeepSeek-TUI adapter

DeepSeek-TUI was renamed CodeWhale. It is an independent community harness,
not an official DeepSeek client, but it retains the `DEEPSEEK_*` hook contract.

Install the engine with `python3 -m pip install .`, then merge `hooks.toml` into
`~/.codewhale/config.toml`. Run `/hooks list` in CodeWhale to confirm the gate.

The adapter maps `require_approval` to `deny` by default. CodeWhale's `ask`
verdict does not downgrade Full Access, so using it as the default would leave a
bypass. Operators who have disabled Full Access may explicitly run
`dpi hook codewhale --codewhale-approval ask` instead.

CodeWhale hooks do not fire in `codewhale exec`, its CLI dispatcher, app-server,
or ACP surfaces. The adapter also denies an argument preview at the documented
10,000-byte cap because the hidden suffix cannot be classified safely.
