/**
 * Advertised product claims — declared once, enforced by a check.
 *
 * On 2 Oct 2026 the size of the ASX universe was written out in nine places
 * across eight files, and the copies disagreed: "2,100+", "2,000+" and
 * "2,000 companies" all described the same 2,121-row universe. The screener's
 * field count disagreed four ways -- "235+", "200+", "80+" and "40+" -- against
 * a live total of 309.
 *
 * None of those were false on the day. That is exactly the problem: a number
 * nobody maintains is true until it quietly isn't, and nothing in the system
 * would have noticed the universe falling through an advertised floor.
 *
 * These are FLOORS, not measurements. The copy says "2,000+" because the claim
 * is "at least this many", which stays true across ordinary movement in the
 * universe. `backend/scripts/assert_marketing_claims.py` checks each floor
 * against the live value and fails if the product has fallen below what the
 * site advertises. The floor is the promise; the check is the proof.
 *
 * Changing a number here changes it everywhere. Do not inline these.
 */

/** Minimum ASX instruments in the served universe. Live: 2,121 on 1 Oct 2026. */
export const UNIVERSE_FLOOR = 2000

/** Minimum filterable fields in the screener. Live: 309 on 2 Oct 2026. */
export const SCREENER_FIELDS_FLOOR = 300

/** Minimum members of the ASX 200. Fixed by index definition. */
export const ASX200_SIZE = 200

const AU = (n: number) => n.toLocaleString('en-AU')

/** "2,000+" — for "screen 2,000+ ASX stocks". */
export const UNIVERSE_CLAIM = `${AU(UNIVERSE_FLOOR)}+`

/** "300+" — for "300+ filterable fields". */
export const SCREENER_FIELDS_CLAIM = `${AU(SCREENER_FIELDS_FLOOR)}+`
