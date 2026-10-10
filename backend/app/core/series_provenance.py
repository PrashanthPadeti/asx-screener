"""
A series whose provenance is not established must not publish figures
=====================================================================
Index code `AXJO` was published as:

    "S&P/ASX 200 Accumulation — the total return version of the S&P/ASX 200
     index, incorporating reinvestment of dividends ... the standard
     benchmark used by Australian superannuation funds"

and populated from `^AXJO`, which is the **price-only** S&P/ASX 200 series.
The producer's own comment said so: "accumulation — same price series as
ASX200 on Yahoo". A total-return surface was served price data.

The codebase does not agree on what the series is even meant to be:

    index_prices.py      "accumulation — same price series as ASX200"
    indices_funds.py     "S&P/ASX 200 Accumulation", ~200 constituents
    three frontend files "AXJO (All Ordinaries, ~500 stocks)"

All Ordinaries is a different index from the S&P/ASX 200. So the correct
replacement cannot be specified yet, let alone verified for return type,
currency, dividend treatment and date coverage — which is why this module
withholds rather than substitutes.

Stored rows are **preserved** for investigation. They are valid price-index
observations; they are not valid for any accumulation calculation, and
nothing may present them as such.

Pure logic, no framework imports, so the containment can be exercised
without standing up the application.
"""

from __future__ import annotations

#: Series code -> why its figures are withheld.
UNVERIFIED_SERIES: dict[str, str] = {
    "AXJO": "series_provenance_unverified",
}

#: Numeric fields withheld for an unverified series.
#:
#: Listed explicitly rather than inferred from the response model: adding a
#: field to IndexPrice must not silently begin publishing it for a series
#: that is suppressed. A new figure defaults to withheld, not to served.
SUPPRESSED_FIELDS = (
    "close_price", "return_1d", "return_1w", "return_1m", "return_3m",
    "return_6m", "return_1y", "return_ytd", "high_52w", "low_52w",
)


# ── Staleness ───────────────────────────────────────────────────────────────
# A different defect from unverified provenance, needing a different remedy.
# AXJO's figures are wrong about WHAT they measure, so everything is withheld.
# ASX100's figures are sound observations that are simply OLD: its last price
# is 2026-05-29 while every other index is current to 2026-10-09.
#
# So the last close and its date are KEPT and labelled historical -- that is
# true and useful -- while anything presented as current is withheld: the
# returns, and the 52-week extremes, which mean "52 weeks to today" by
# implication and were last computed in May.

STALE = "stale"

#: Withheld for a stale series. `close_price` and `price_date` are retained.
STALE_SUPPRESSED_FIELDS = (
    "return_1d", "return_1w", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_ytd", "high_52w", "low_52w",
)

#: Trading sessions of silence before a series is stale.
#:
#: Public holidays are not modelled, and the ASX has single-day closures plus
#: Easter's four-day gap. Three sessions absorbs those without masking a real
#: outage -- the defect this exists to catch ran to roughly 94 sessions.
STALE_AFTER_SESSIONS = 3


def last_expected_session(today):
    """The most recent weekday whose close should already be published.

    Never `today`: a session's data lands after the close, so expecting it on
    the day would mark every index stale each morning. Walks back over
    weekends, so a Saturday expects Friday and a Monday expects Friday.

    Weekday-based, not calendar-based. A calendar threshold either fires every
    weekend or has to be loosened until it stops catching anything.
    """
    from datetime import timedelta                              # noqa: PLC0415
    day = today - timedelta(days=1)
    while day.weekday() >= 5:            # 5 = Saturday, 6 = Sunday
        day -= timedelta(days=1)
    return day


def sessions_behind(price_date, today) -> int:
    """Weekdays between a price date and the last expected session.

    Holidays count as sessions here, which is why the threshold allows a few.
    Over-counting slightly is safe; under-counting hides staleness.
    """
    from datetime import timedelta                              # noqa: PLC0415
    if price_date is None:
        return 10 ** 6
    target = last_expected_session(today)
    if price_date >= target:
        return 0
    n, day = 0, price_date
    while day < target:
        day += timedelta(days=1)
        if day.weekday() < 5:
            n += 1
    return n


def is_stale(price_date, today) -> bool:
    return sessions_behind(price_date, today) > STALE_AFTER_SESSIONS


def suppress_if_stale(values: dict, today) -> dict:
    """Withhold whatever a stale series would present as current.

    Returns the input unchanged when the series is fresh, so it is applied to
    every index rather than to a hand-maintained list. Staleness is MEASURED,
    not declared -- which is what makes it catch the next series to go quiet,
    rather than only the one already known about.
    """
    import datetime as _dt                                      # noqa: PLC0415
    if values.get("data_status"):
        # Provenance outranks staleness. An unverified series has already had
        # everything withheld, and relabelling it "stale" would understate
        # the problem -- stale means "these figures are old", which implies
        # they were right when fresh.
        return values
    raw = values.get("price_date")
    if isinstance(raw, str):
        try:
            raw = _dt.date.fromisoformat(raw[:10])
        except ValueError:
            return values
    if raw is None or not is_stale(raw, today):
        return values
    out = dict(values)
    for field in STALE_SUPPRESSED_FIELDS:
        if field in out:
            out[field] = None
    out["data_status"] = STALE
    out["sessions_behind"] = sessions_behind(raw, today)
    return out


def containment_version() -> str:
    """A short digest of the suppression rules, for cache keys.

    `asx:indices:list` is cached for an hour on a static key, so deploying
    containment would otherwise keep serving pre-containment figures for up
    to an hour — the suppression would appear not to work, and the obvious
    conclusion ("the code is wrong") would be false.

    Derived rather than hand-bumped: changing UNVERIFIED_SERIES or
    SUPPRESSED_FIELDS changes the key automatically. A version constant
    someone has to remember to increment is a version constant that
    eventually is not incremented.
    """
    import hashlib                                              # noqa: PLC0415
    material = (repr(sorted(UNVERIFIED_SERIES.items())) + repr(SUPPRESSED_FIELDS)
                + repr(STALE_SUPPRESSED_FIELDS) + repr(STALE_AFTER_SESSIONS))
    return hashlib.sha256(material.encode()).hexdigest()[:8]


def is_unverified(code: str) -> bool:
    return code.upper() in UNVERIFIED_SERIES


def suppress_if_unverified(code: str, values: dict) -> dict:
    """Withhold every numeric field for a series we cannot substantiate.

    `price_date` is retained deliberately. It says when the underlying rows
    stop, which is what an investigator needs, and it is not a figure anyone
    can mistake for a return.

    `data_status` is set so a consumer can distinguish "we have no figure"
    from "we have a figure we cannot stand behind". Without it, suppression
    is indistinguishable from an outage, and an outage invites a retry.
    """
    reason = UNVERIFIED_SERIES.get(code.upper())
    if reason is None:
        return values
    out = dict(values)
    for field in SUPPRESSED_FIELDS:
        if field in out:
            out[field] = None
    out["data_status"] = reason
    return out
