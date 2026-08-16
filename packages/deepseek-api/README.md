# DeepSeek API adapter

DeepSeek is primarily a model/API provider rather than one universal coding
harness. For an application-owned tool loop, call `authorize_tool_call` before
dispatching every function call returned by the model.

The host application must provide the approval UI. Without an approval callback,
`require_approval` fails closed. This adapter cannot protect the DeepSeek web UI
or a third-party harness that does not route all tool calls through it.
