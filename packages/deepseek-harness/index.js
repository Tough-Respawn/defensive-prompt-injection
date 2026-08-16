import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'defensive-prompt-injection'
export const inject = ['tools']

const PLUGIN_ROOT = dirname(fileURLToPath(import.meta.url))
const RUNTIME_ROOT = join(PLUGIN_ROOT, 'runtime')
const MAX_OUTPUT_BYTES = 1024 * 1024
const POLICY_TIMEOUT_MS = 10_000
const PYTHON_BOOTSTRAP = 'import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("dpi",run_name="__main__")'

function deny(reason) {
  return {
    kind: 'deny',
    reason: `Defensive prompt-injection runtime failed closed (${reason}).`,
  }
}

function pythonCommand() {
  if (process.env.DPI_PYTHON) return [process.env.DPI_PYTHON, []]
  return process.platform === 'win32' ? ['py', ['-3']] : ['python3', []]
}

function runPolicy(payload, signal) {
  return new Promise((resolve) => {
    const [executable, prefixArgs] = pythonCommand()
    let child

    try {
      child = spawn(
        executable,
        [
          ...prefixArgs,
          '-I',
          '-S',
          '-c',
          PYTHON_BOOTSTRAP,
          RUNTIME_ROOT,
          'hook',
          'deepseek-harness',
          '--output',
          'canonical',
        ],
        {
          cwd: PLUGIN_ROOT,
          env: process.env,
          stdio: ['pipe', 'pipe', 'pipe'],
          windowsHide: true,
        },
      )
    } catch {
      resolve(deny('policy process could not start'))
      return
    }

    let settled = false
    let stdout = ''
    let outputBytes = 0
    let limitExceeded = false
    let timedOut = false
    let aborted = false

    const finish = (decision) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
      resolve(decision)
    }

    const stop = () => {
      if (!child.killed) child.kill()
    }

    const onAbort = () => {
      aborted = true
      stop()
    }

    const timer = setTimeout(() => {
      timedOut = true
      stop()
    }, POLICY_TIMEOUT_MS)

    child.on('error', () => finish(deny('policy process error')))
    child.stdout.on('data', (chunk) => {
      outputBytes += chunk.length
      if (outputBytes > MAX_OUTPUT_BYTES) {
        limitExceeded = true
        stop()
        return
      }
      stdout += chunk.toString('utf8')
    })
    child.stderr.on('data', (chunk) => {
      outputBytes += chunk.length
      if (outputBytes > MAX_OUTPUT_BYTES) {
        limitExceeded = true
        stop()
      }
    })
    child.on('close', (code) => {
      if (aborted) return finish(deny('call aborted during policy evaluation'))
      if (timedOut) return finish(deny('policy timeout'))
      if (limitExceeded) return finish(deny('policy output limit exceeded'))
      if (code !== 0) return finish(deny('policy process exited nonzero'))

      try {
        const result = JSON.parse(stdout)
        const action = result?.action
        const decision = result?.decision
        const validEffect = ['allow', 'require_approval', 'deny'].includes(decision?.effect)
        const callMatches = action?.harness === 'deepseek-harness'
          && action?.tool_name === payload.tool_name
          && JSON.stringify(action?.arguments) === JSON.stringify(payload.arguments)
        const protocolMatches = action?.protocol_version === 1
          && decision?.protocol_version === 1

        if (!validEffect || !callMatches || !protocolMatches) {
          return finish(deny('invalid policy response'))
        }
        finish(decision)
      } catch {
        finish(deny('unparseable policy response'))
      }
    })

    if (signal?.aborted) onAbort()
    else signal?.addEventListener('abort', onAbort, { once: true })

    try {
      child.stdin.end(JSON.stringify(payload))
    } catch {
      stop()
      finish(deny('tool call could not be serialized'))
    }
  })
}

export function apply(ctx) {
  ctx.on('tools/pre-execute', async (exec, next) => {
    let decision
    try {
      decision = await runPolicy(
        { tool_name: exec.name, arguments: exec.arguments },
        exec.signal,
      )
    } catch {
      return deny('unexpected policy failure')
    }

    if (decision.kind === 'deny') return decision
    if (decision.effect === 'allow') return next()

    const reason = decision.reason
      ?? `Defensive prompt-injection [${decision.rule_id ?? 'unknown-risk'}]: ${decision.message ?? 'operation blocked'}`
    if (decision.effect === 'require_approval') return { kind: 'ask', reason }
    if (decision.effect === 'deny') return { kind: 'deny', reason }
    return deny('unknown policy decision')
  }, { prepend: true })
}
