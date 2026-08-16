import assert from 'node:assert/strict'

import { apply } from '../packages/deepseek-harness/index.js'

let preExecute
const ctx = {
  on(event, handler, options) {
    assert.equal(event, 'tools/pre-execute')
    assert.deepEqual(options, { prepend: true })
    preExecute = handler
  },
}

apply(ctx)
assert.equal(typeof preExecute, 'function')

let delegated = 0
const harmless = await preExecute(
  {
    name: 'read',
    arguments: { path: '/work/src/app.py' },
    signal: new AbortController().signal,
  },
  async () => {
    delegated += 1
    return { kind: 'downstream-policy-result' }
  },
)
assert.deepEqual(harmless, { kind: 'downstream-policy-result' })
assert.equal(delegated, 1)

const sensitive = await preExecute(
  {
    name: 'read',
    arguments: { path: '/home/alice/.dsh/.credentials.yaml' },
    signal: new AbortController().signal,
  },
  async () => {
    delegated += 1
    return { kind: 'should-not-run' }
  },
)
assert.equal(sensitive.kind, 'ask')
assert.match(sensitive.reason, /sensitive-data/)
assert.equal(delegated, 1)

const originalPython = process.env.DPI_PYTHON
process.env.DPI_PYTHON = '/definitely/missing/dpi-python'
const unavailableRuntime = await preExecute(
  {
    name: 'read',
    arguments: { path: '/work/src/app.py' },
    signal: new AbortController().signal,
  },
  async () => {
    delegated += 1
    return { kind: 'should-not-run' }
  },
)
if (originalPython === undefined) delete process.env.DPI_PYTHON
else process.env.DPI_PYTHON = originalPython

assert.equal(unavailableRuntime.kind, 'deny')
assert.match(unavailableRuntime.reason, /failed closed/)
assert.equal(delegated, 1)

console.log('DeepSeek Harness adapter: 3 passed')
