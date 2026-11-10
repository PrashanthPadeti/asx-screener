/**
 * The operator rule, exercised against the real module.
 *
 * Run:  node --experimental-strip-types --no-warnings lib/screener-operators.test.mts
 *
 * The load-bearing case is the FIRST one: a field whose metadata has not
 * arrived keeps its operator. That is the whole of the customer-reported bug.
 * Treating an unknown field as text made `gte` invalid, the correction wrote
 * `eq` into state, and every preset opened reading "=" and matched nothing.
 *
 * The presets below are the real ones from the API, including
 * small_cap_hidden_gems, which is the screen in the customer's screenshot.
 */

import assert from 'node:assert/strict'
import { OPERATORS, operatorFor, operatorsForType } from './screener-operators.ts'

let passed = 0
const failures: string[] = []
function test(name: string, fn: () => void) {
  try { fn(); passed++; console.log(`  PASS  ${name}`) }
  catch (e) { failures.push(name); console.log(`  FAIL  ${name}  - ${(e as Error).message}`) }
}

/** small_cap_hidden_gems, verbatim from the presets endpoint. */
const CUSTOMER_PRESET = [
  { field: 'market_cap', operator: 'gte', value: 50 },
  { field: 'market_cap', operator: 'lte', value: 500 },
  { field: 'piotroski_f_score', operator: 'gte', value: 7 },
  { field: 'revenue_growth_1y', operator: 'gte', value: 20 },
  { field: 'net_margin', operator: 'gte', value: 5 },
  { field: 'debt_to_equity', operator: 'lte', value: 0.5 },
]

// ── The regression ──────────────────────────────────────────────────────────

test('a preset keeps every operator while the field list is still loading', () => {
  for (const f of CUSTOMER_PRESET) {
    assert.equal(operatorFor(f.operator, undefined), f.operator,
      `${f.field} lost its ${f.operator} before the metadata arrived`)
  }
})

test('not one preset operator degrades to eq while loading', () => {
  const degraded = CUSTOMER_PRESET
    .filter(f => operatorFor(f.operator, undefined) === 'eq' && f.operator !== 'eq')
    .map(f => f.field)
  assert.deepEqual(degraded, [],
    'these would render "=" and match nothing, which is the reported bug')
})

test('the same operators survive once the fields arrive as numbers', () => {
  for (const f of CUSTOMER_PRESET) {
    assert.equal(operatorFor(f.operator, 'number'), f.operator)
  }
})

// ── Unknown is not text ─────────────────────────────────────────────────────

test('an unknown field type is not treated as text', () => {
  // 'gte' is invalid for text and valid for a number. If unknown collapsed to
  // text, this would return 'eq' — exactly how the bug was introduced.
  assert.equal(operatorFor('gte', undefined), 'gte')
  assert.equal(operatorFor('gte', 'text'), 'eq')
})

test('a field genuinely absent from a loaded list is still left alone', () => {
  // The caller passes undefined for "not in the metadata", whether that is
  // because nothing loaded or because this field is not in it. Either way the
  // stored choice is better evidence than a guess.
  assert.equal(operatorFor('lte', undefined), 'lte')
})

// ── Real mismatches are still corrected ─────────────────────────────────────

test('an operator a known type cannot take is normalised', () => {
  assert.equal(operatorFor('gte', 'text'), 'eq')
  assert.equal(operatorFor('lt', 'boolean'), 'eq')
})

test('a valid operator is never rewritten', () => {
  assert.equal(operatorFor('neq', 'text'), 'neq')
  assert.equal(operatorFor('eq', 'boolean'), 'eq')
  assert.equal(operatorFor('lt', 'number'), 'lt')
})

// ── The vocabulary itself ───────────────────────────────────────────────────

test('number rows default to >= rather than =', () => {
  // A new numeric filter defaulting to equality is the same defect by a
  // different route: nobody screens for an exact market cap.
  assert.equal(OPERATORS.number[0].value, 'gte')
  assert.equal(OPERATORS.number[0].label, '>=')
})

test('every operator the presets use is a valid number operator', () => {
  const valid = new Set(OPERATORS.number.map(o => o.value))
  for (const f of CUSTOMER_PRESET) {
    assert.ok(valid.has(f.operator),
      `${f.operator} is not offered for numbers, so ${f.field} could never show it`)
  }
})

test('an unrecognised type falls back to text, and that is a real fallback', () => {
  assert.deepEqual(operatorsForType('nonsense'), OPERATORS.text)
  assert.deepEqual(operatorsForType(undefined), OPERATORS.text)
})

console.log(`\n${passed}/${passed + failures.length} passed`)
if (failures.length) process.exit(1)
