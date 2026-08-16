import { spawnSync } from "node:child_process"
import { Plugin } from "@opencode-ai/plugin"

export default Plugin.define({
  id: "defensive-prompt-injection",
  setup: async (ctx) => {
    await ctx.tool.hook("execute.before", (event) => {
      const payload = JSON.stringify({ tool_name: event.tool, tool_input: event.input })
      const result = spawnSync("dpi", ["hook", "opencode", "--output", "canonical"], {
        input: payload,
        encoding: "utf8",
        timeout: 10_000,
      })

      if (result.error || result.status !== 0 || !result.stdout.trim()) {
        throw new Error("Defensive prompt-injection policy runtime failed closed")
      }

      const output = JSON.parse(result.stdout)
      if (output.decision?.effect !== "allow") {
        throw new Error(
          `Defensive prompt-injection blocked ${output.decision?.rule_id ?? "unknown-risk"}`,
        )
      }
    })
  },
})
