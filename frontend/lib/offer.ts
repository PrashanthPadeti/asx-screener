/**
 * Founding-member offer deadline — declared once.
 *
 * Until 2 Oct 2026 the end date was written out as prose in five places
 * across app/page.tsx and app/pricing/page.tsx. Nothing connected them, so
 * when the deadline passed on 30 Sep the site kept advertising "Offer ends
 * September 2026" to every visitor, a day into October. An expired deadline
 * on a paid plan is not a cosmetic bug.
 *
 * Change ENDS_AT and every banner follows. `offerHasEnded()` exists so a
 * passed deadline can be detected rather than merely re-read by a human.
 */

/** Last moment the offer is valid, in Australian Eastern time. */
export const OFFER_ENDS_AT = new Date('2026-09-30T23:59:59+10:00')

/** Long form, e.g. for body copy: "offer ends September 2026". */
export const OFFER_ENDS_LONG = OFFER_ENDS_AT.toLocaleDateString('en-AU', {
  month: 'long', year: 'numeric', timeZone: 'Australia/Sydney',
})

/** Short form, for badges: "Sep 2026". */
export const OFFER_ENDS_SHORT = OFFER_ENDS_AT.toLocaleDateString('en-AU', {
  month: 'short', year: 'numeric', timeZone: 'Australia/Sydney',
})

/** True once the deadline has passed. */
export function offerHasEnded(now: Date = new Date()): boolean {
  return now > OFFER_ENDS_AT
}
