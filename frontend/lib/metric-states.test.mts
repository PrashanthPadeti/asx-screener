/**
 * The resolver, exercised against the real module.
 *
 * Run:  npm run test:units
 *       (node --experimental-strip-types, no test framework)
 *
 * The load-bearing case is alias resolution. The applicability sidecar is
 * keyed by CANONICAL metric name and a row's values are keyed by PHYSICAL
 * column; for 8 of the 72 governed metrics those differ. row_projection.py
 * records that this is "how ev_to_ebitda escaped assessment once already", so
 * ev_to_ebitda -> ev_ebitda is the regression case, not an afterthought.
 */

import assert from 'node:assert/strict'
import { resolveMetric, explanationText, stateLabel } from './metric-states.ts'
import type { MetricExplanation } from './metric-states.ts'

let passed = 0
const failures: string[] = []
function test(name: string, fn: () => void) {
  try { fn(); passed++; console.log(`  PASS  ${name}`) }
  catch (e) { failures.push(name); console.log(`  FAIL  ${name}  - ${(e as Error).message}`) }
}

// The sidecar as the API sends it: keyed canonically.
const PE: MetricExplanation = {
  state: 'not_meaningful',
  cause: 'unit_mismatch',
  reason: 'price is quoted in AUD and earnings per share are stated in USD; '
        + 'the ratio has no unit until one side is converted',
}
const EV: MetricExplanation = {
  state: 'not_meaningful',
  cause: 'unit_mismatch',
  reason: 'enterprise value is derived from an AUD market capitalisation and '
        + 'EBITDA is stated in USD',
}
const states = { pe_ratio: PE, ev_ebitda: EV }

// Column -> canonical, exactly as GET /screener/fields publishes it.
const governed = {
  pe_ratio:     'pe_ratio',
  ev_to_ebitda: 'ev_ebitda',      // the spellings that differ
  dps_ttm:      'dividend_per_share',
  roe:          'roe',
}

// ── The adversarial fixture ──────────────────────────────────────────────────

test('ev_to_ebitda surfaces the state stored under ev_ebitda', () => {
  const r = resolveMetric('ev_to_ebitda', false, states, governed)
  assert.equal(r.kind, 'explained')
  assert.equal((r as any).explanation.cause, 'unit_mismatch')
  assert.match((r as any).explanation.reason, /EBITDA is stated in USD/)
})

test('a direct lookup by column name would have missed it', () => {
  // The control: without the published map, ev_to_ebitda finds nothing.
  // This is the defect the mapping exists to prevent, stated as a test.
  assert.equal((states as any)['ev_to_ebitda'], undefined)
})

test('identity-mapped metrics still resolve', () => {
  const r = resolveMetric('pe_ratio', false, states, governed)
  assert.equal(r.kind, 'explained')
  assert.match((r as any).explanation.reason, /no unit until one side is converted/)
})

// ── The four absence semantics ───────────────────────────────────────────────

test('value present -> show the value', () => {
  assert.equal(resolveMetric('pe_ratio', true, states, governed).kind, 'value')
})

test('an applicable metric shows no explanation', () => {
  // roe is governed and mapped, but the sparse sidecar has no entry, which
  // means APPLICABLE. A tooltip here would invent a claim.
  assert.equal(resolveMetric('roe', false, states, governed).kind, 'plain')
})

test('null with no sidecar entry stays a plain dash', () => {
  assert.equal(resolveMetric('dps_ttm', false, states, governed).kind, 'plain')
})

test('an ungoverned field never claims a reason', () => {
  assert.equal(resolveMetric('company_name', false, states, governed).kind, 'plain')
})

test('a missing map fails CLOSED rather than guessing', () => {
  // Without the map, guessing that the column name doubles as the canonical
  // name would be right 64 times out of 72 and quietly wrong 8 times.
  const r = resolveMetric('ev_to_ebitda', false, states, null)
  assert.equal(r.kind, 'unmapped')
})

test('no states at all is plain, not unmapped', () => {
  assert.equal(resolveMetric('pe_ratio', false, null, governed).kind, 'plain')
})

// ── Presentation leads with the persisted reason ─────────────────────────────

test('the reason is shown, not the enum', () => {
  const text = explanationText(PE)
  assert.match(text, /^price is quoted in AUD/)
  assert.ok(!text.includes('not_meaningful'), 'leaked an internal enum')
  assert.ok(!text.includes('unit_mismatch'), 'leaked an internal enum')
})

test('the engine sentence is used verbatim', () => {
  assert.equal(explanationText(PE), PE.reason)
})

test('a state with no reason still says something', () => {
  const bare: MetricExplanation = { state: 'unavailable', cause: 'source_missing', reason: '' }
  assert.equal(explanationText(bare), 'Unavailable')
})

test('state labels are human words', () => {
  for (const s of ['not_meaningful', 'unavailable', 'insufficient_data'] as const) {
    assert.ok(!stateLabel(s).includes('_'), `${s} label leaks the enum`)
  }
})

console.log(`\n${passed}/${passed + failures.length} passed`)
if (failures.length) process.exit(1)
