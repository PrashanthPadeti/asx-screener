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
 * A dash that explains itself is the argument for the product. A dash that
 * does not looks like a gap.
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

/**
 * The explanation for one field, or null when the value simply stands.
 *
 * Absence of an entry means APPLICABLE — the sidecar is sparse by design, so
 * "no entry" is a statement, not a missing one.
 */
export function explain(
  states: MetricStates,
  field: string,
): MetricExplanation | null {
  if (!states) return null
  return states[field] ?? null
}

/** A short label for the state, in the reader's language rather than the engine's. */
export function stateLabel(state: MetricState): string {
  switch (state) {
    case 'not_meaningful':    return 'Not meaningful here'
    case 'unavailable':       return 'Unavailable'
    case 'insufficient_data': return 'Not enough history'
    default:                  return 'Available'
  }
}

/**
 * The full sentence shown on hover.
 *
 * The engine's `reason` is already written for a reader, so it is used as
 * given rather than paraphrased — paraphrasing is how a precise statement
 * becomes an approximate one.
 */
export function explanationText(e: MetricExplanation): string {
  const head = stateLabel(e.state)
  const body = e.reason?.trim()
  return body ? `${head} — ${body}` : head
}
