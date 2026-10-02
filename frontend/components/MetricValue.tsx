import { explain, explanationText, stateLabel } from '@/lib/metric-states'
import type { MetricStates } from '@/lib/metric-states'

/**
 * A governed metric: the value when it stands, an explained dash when it does
 * not.
 *
 * Deliberately a server component with no client JavaScript. The explanation
 * rides on `title`, so it is present in the HTML a crawler and a screen reader
 * receive, and it works before hydration — the same reason the rest of this
 * release moved content out of the RSC payload and into markup.
 *
 * The dotted underline is the only affordance: it marks the dash as something
 * that will answer a question, which a plain em dash does not.
 */
export function MetricValue({
  value,
  field,
  states,
  className = '',
}: {
  /** Already-formatted display string, or null when the engine withheld it. */
  value: string | null
  /** The metric's key in the sidecar, e.g. "pe_ratio". */
  field: string
  states: MetricStates
  className?: string
}) {
  if (value !== null && value !== '—') {
    return <span className={className}>{value}</span>
  }

  const e = explain(states, field)
  if (!e) {
    // No value and no entry: nothing was asserted about this field, so claim
    // nothing. Inventing "unavailable" here would be the same error in
    // miniature as inventing the number.
    return <span className={`text-gray-400 ${className}`}>—</span>
  }

  return (
    <abbr
      title={explanationText(e)}
      aria-label={explanationText(e)}
      className={`text-gray-400 no-underline decoration-dotted underline-offset-4
                  decoration-gray-300 [text-decoration-line:underline] cursor-help ${className}`}
      data-metric-state={e.state}
      data-metric-cause={e.cause}
    >
      —<span className="sr-only"> {stateLabel(e.state)}</span>
    </abbr>
  )
}
