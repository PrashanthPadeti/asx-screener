import { resolveMetric, explanationText, stateLabel } from '@/lib/metric-states'
import type { GovernedColumns, MetricStates } from '@/lib/metric-states'

/**
 * A governed metric: the value when it stands, an explained dash when it does
 * not.
 *
 * Deliberately carries no client JavaScript. The explanation rides on `title`
 * and `aria-label`, so it is present in the HTML a crawler and a screen reader
 * receive and it works before hydration — the same reason this release moved
 * page content out of the RSC payload and into markup.
 *
 * The dotted underline is the only affordance: it marks the dash as something
 * that will answer a question, which a plain em dash does not. A dash with
 * nothing to say stays plain, so the affordance never promises an explanation
 * that isn't there.
 *
 * Presentation leads with the engine's persisted sentence. The state and cause
 * enums are implementation vocabulary; they stay on data attributes for
 * diagnostics rather than being shown as the primary text.
 */
export function MetricValue({
  value,
  field,
  states,
  governed,
  className = '',
}: {
  /** Already-formatted display node, or null when the engine withheld it. */
  value: React.ReactNode | null
  /** The field's display/column name. Canonical lookup happens inside. */
  field: string
  states: MetricStates
  /** Column -> canonical map from GET /screener/fields. Never built locally. */
  governed: GovernedColumns
  className?: string
}) {
  const hasValue = value !== null && value !== undefined && value !== '—'
  const r = resolveMetric(field, hasValue, states, governed)

  if (r.kind === 'value') return <>{value}</>

  // 'plain' and 'unmapped' both render a dash that claims nothing. They are
  // kept distinct in the resolver because only 'unmapped' indicates the
  // canonical map failed to load — a condition worth seeing in diagnostics
  // rather than silently equating with "nothing was asserted".
  if (r.kind !== 'explained') {
    return (
      <span className={`text-gray-400 ${className}`}
            data-metric-resolution={r.kind}>—</span>
    )
  }

  const text = explanationText(r.explanation)
  return (
    <abbr
      title={text}
      aria-label={`${stateLabel(r.explanation.state)}: ${text}`}
      className={`text-gray-400 decoration-dotted underline-offset-4 decoration-gray-300
                  [text-decoration-line:underline] cursor-help ${className}`}
      data-metric-state={r.explanation.state}
      data-metric-cause={r.explanation.cause}
    >
      —
    </abbr>
  )
}
