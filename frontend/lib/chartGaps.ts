/**
 * Break a time series where sessions are missing.
 *
 * Absent days are not present in the data at all — a fund or index that
 * stopped publishing simply has no rows for that period. Recharts therefore
 * plots the last point before the hole adjacent to the first point after it
 * and joins them, drawing an unbroken line across sessions that were never
 * recorded.
 *
 * ASX100 stopped on 2026-05-29 and resumes from 2026-10-13; eight funds
 * stopped in June 2026 and resume when restored. In both cases the chart
 * would imply ~95 sessions of continuity that do not exist.
 *
 * Inserting an explicit null point makes Recharts leave the gap visible,
 * because `connectNulls` defaults to false. A gap in the data should look
 * like a gap.
 *
 * This lives in one place because the same defect was fixed once for the
 * index chart and then found again, unfixed, in the fund chart.
 */

/** A long weekend plus a public holiday. Longer than this is a real gap. */
export const MAX_GAP_DAYS = 5

export interface SeriesGap {
  from: string
  to: string
  days: number
}

/**
 * Returns the points with null breaks inserted, and the gaps that were found.
 *
 * The null row carries a synthetic `date` label so Recharts has a distinct
 * category for it; every other field is null, which is what breaks the line.
 */
export function insertGaps<T extends { date: string }>(
  points: T[],
  maxGapDays: number = MAX_GAP_DAYS,
): { points: (T | { date: string })[]; gaps: SeriesGap[] } {
  const out: (T | { date: string })[] = []
  const gaps: SeriesGap[] = []

  points.forEach((pt, i) => {
    if (i > 0) {
      const prev = points[i - 1]
      const days = Math.round(
        (new Date(pt.date).getTime() - new Date(prev.date).getTime()) / 86400000,
      )
      if (days > maxGapDays) {
        out.push({ date: `${prev.date}..${pt.date}` })
        gaps.push({ from: prev.date, to: pt.date, days })
      }
    }
    out.push(pt)
  })

  return { points: out, gaps }
}

/** One sentence per gap. A break with no caption reads as a rendering bug. */
export function describeGaps(gaps: SeriesGap[]): string {
  return gaps
    .map(g => `${g.from} to ${g.to} (${g.days} days, no data recorded)`)
    .join('; ')
}
