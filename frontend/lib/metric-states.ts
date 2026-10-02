/**
 * Read the applicability sidecar the API already sends.
 *
 * Every screener row carries `metric_states`: for each governed metric the
 * engine declined to publish, the state, the cause, and a sentence explaining
 * it. BHP's P/E, for instance:
 *
 *   state   not_meaningful
 *   cause   unit_mismatch
 *   reason  "price is quoted in AUD and earnings per share are stated in USD;
 *            the ratio has no unit until one side is converted"
 *
 * Until 2 Oct 2026 the frontend discarded all of it and rendered a bare dash,
 * so the single most defensible thing this product does — refusing to serve a
 * number it cannot substantiate — was indistinguishable from missing data.
 *
 * ── Canonical identity is consumed here, never declared ──────────────────────
 * The sidecar is keyed by CANONICAL metric name; a row's values are keyed by
 * PHYSICAL column. For 8 of the 72 governed metrics those differ
 * (ev_ebitda/ev_to_ebitda, dividend_per_share/dps_ttm, ...). The mapping comes
 * from GET /api/v1/screener/fields — `canonical_metric` on each descriptor and
 * the complete `governed_columns` map — and is never restated in this file.
 * An alias table here would be a second authority for identity, which is how
 * ev_to_ebitda escaped assessment once already.
 */

export type MetricState =
  | 'applicable'
  | 'not_meaningful'
  | 'unavailable'
  | 'insufficient_data'

export type MetricExplanation = {
  state: MetricState
  cause: string
  reason: string
}

export type MetricStates = Record<string, MetricExplanation> | null | undefined

/** Physical column -> canonical metric, exactly as the API published it. */
export type GovernedColumns = Record<string, string> | null | undefined

/** The four ways a cell can resolve. Distinguished because they are not the same fact. */
export type Resolution =
  | { kind: 'value' }                                   // the value stands
  | { kind: 'explained'; explanation: MetricExplanation } // withheld, with a reason
  | { kind: 'plain' }                                   // null, nothing asserted
  | { kind: 'unmapped' }                                // no canonical key: fail closed

/**
 * Resolve one cell.
 *
 * `field` is the display/column name. The canonical key is looked up in the
 * backend-supplied map — when that map has no entry for a field the engine
 * governs, the explanation path fails CLOSED and renders a plain dash, rather
 * than guessing that the column name doubles as the canonical one. Guessing
 * would be right 64 times out of 72 and quietly wrong 8 times.
 */
export function resolveMetric(
  field: string,
  hasValue: boolean,
  states: MetricStates,
  governed: GovernedColumns,
): Resolution {
  if (hasValue) return { kind: 'value' }
  if (!states) return { kind: 'plain' }

  // An ungoverned field has no canonical key and never carries a state.
  const canonical = governed?.[field]
  if (!canonical) {
    return governed ? { kind: 'plain' } : { kind: 'unmapped' }
  }

  const explanation = states[canonical]
  // Governed, null, and no entry: the sidecar is sparse by design, so this is
  // "nothing was asserted", not "unavailable". Claiming a cause we were not
  // given would be the same error as inventing the number.
  return explanation ? { kind: 'explained', explanation } : { kind: 'plain' }
}

/**
 * A short label for the state, in the reader's language rather than the engine's.
 * Supporting text only — the persisted reason leads.
 */
export function stateLabel(state: MetricState): string {
  switch (state) {
    case 'not_meaningful':    return 'Withheld'
    case 'unavailable':       return 'Unavailable'
    case 'insufficient_data': return 'Not enough history'
    default:                  return 'Available'
  }
}

/**
 * What the reader sees.
 *
 * Leads with the engine's own sentence, used verbatim. That sentence is the
 * contract a person can actually understand; `not_meaningful` and
 * `unit_mismatch` are implementation vocabulary and stay out of the primary
 * presentation. They remain on the element as data attributes for diagnostics.
 */
export function explanationText(e: MetricExplanation): string {
  const reason = e.reason?.trim()
  return reason || stateLabel(e.state)
}
