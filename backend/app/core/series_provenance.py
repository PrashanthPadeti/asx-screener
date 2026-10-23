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

#: What a stale label does NOT say.
#:
#: Marking a series stale asserts exactly one thing: it has stopped updating.
#: It is NOT a statement that the stored values are correct, and it closes no
#: question about the series' source or identity. ASX100's retained close and
#: chart are shown because they are what was recorded, not because anything
#: here has verified what they measure -- that question is open and tracked
#: separately. Retention is not endorsement.

#: Withheld for a stale series. `close_price` and `price_date` are retained.
STALE_SUPPRESSED_FIELDS = (
    "return_1d", "return_1w", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_ytd", "high_52w", "low_52w",
)

#: The market whose sessions define freshness, and when its close is
#: expected to have been published.
#:
#: The ASX closes at 16:00 Sydney; vendor files settle afterwards. 18:00 is
#: the documented cutoff: BEFORE it, today's close is not yet expected;
#: AFTER it, it is. Without a cutoff the rule has to either expect today's
#: close from midnight -- marking every index stale each morning -- or never
#: expect it, which leaves a permanent one-session lag: on Monday evening,
#: hours after Monday's close was published, the system would still consider
#: Friday's data current.
MARKET_TZ = "Australia/Sydney"
PUBLICATION_CUTOFF_HOUR = 18

#: FRESHNESS AND ALERT TOLERANCE ARE SEPARATE, and conflating them is how a
#: series that has missed a session keeps reporting itself current.
#:
#:   0 sessions behind          current      no marking
#:   1..STALE_AFTER_SESSIONS    delayed      marked, figures still shown
#:   > STALE_AFTER_SESSIONS     stale        marked, current-figures withheld
#:
#: An earlier version used one threshold for both, so Monday's missing close
#: read as "current" until Thursday. The clock was right and the label was
#: still wrong: *whether a session is missing* is a fact, while *how long to
#: tolerate it before withholding figures* is an operational choice. Only the
#: second is a judgement call, and it must not silently redefine the first.
#:
#: The tolerance governs WITHHOLDING, and nothing else. There is no
#: operational alerting on freshness in this system; if one is added it may
#: well want a different threshold, and should not assume this one.
#:
#: It is not a substitute for a holiday calendar either. Holidays are not
#: modelled, so a closure consumes part of the tolerance; three sessions
#: covers the ASX's single-day closures and the four-day Easter gap. Nor is
#: it a judgement that three sessions of silence is acceptable -- the defect
#: it exists to catch ran to roughly 94.
STALE_AFTER_SESSIONS = 3

DELAYED = "delayed"

#: No price has ever been recorded for this series.
#:
#: Distinct from stale, which means "it stopped". Never-published and
#: stopped-publishing have different causes -- a dead identifier versus a
#: source that went quiet -- and collapsing them loses the distinction that
#: tells an operator where to look. Before this existed, a series with no
#: prices returned no status at all, i.e. "current": the same defect as
#: deriving freshness from a window that excluded everything.
NO_DATA = "no_data"

#: Recorded source changes, surfaced so a chart can say where a series stops
#: being one provider's data and starts being another's.
#:
#: A series spanning a provider change is not a lie, but a chart that renders
#: it as one unbroken line implies a continuity that does not exist. ASX100's
#: configured Yahoo symbol stopped returning data on 2026-05-29; EODHD takes
#: over from the switch date, and the sessions between are absent entirely.
#: Date ranges where the stored series is KNOWN to hold the wrong data.
#:
#: Distinct from UNVERIFIED_SERIES, which says "we cannot substantiate this
#: series at all" and withholds every figure. Here the series is sound
#: outside a bounded window and wrong inside it, so withholding everything
#: would discard four years of correct history to hide thirteen months of
#: bad. The figures stay; the chart says which stretch not to trust.
#:
#: Measured 19 Oct 2026 over 1,351 sessions: each of these three agrees with
#: its correctly-named EODHD symbol at 0.00000% before 2025-05 and after
#: 2026-05, and diverges throughout the window -- ASX20 by ~46% (it holds
#: the All Ordinaries), AXFJ by ~31,000%, AXMJ by ~138,000%.
#:
#: Served numbers are NOT affected: returns and 52-week extremes are derived
#: from the freshly fetched frame, never from these rows. The chart is,
#: because it plots stored history.
#:
#: This entry is removed when the repair lands, not before. Removing it
#: while the rows are still wrong would be the quietest possible way to
#: reintroduce the defect.
#: See docs/finding_2026-10-19_three_indices_wrong_for_13_months.md
#: Empty since 21 Oct 2026. The three entries it held were removed when the
#: rows behind them were repaired -- not before. The mechanism stays: a
#: bounded stretch of wrong data is a thing that can happen again, and the
#: next one should be declarable without rebuilding this.
KNOWN_BAD_WINDOWS: dict[str, dict] = {}

#: History that has been RESTATED, and when.
#:
#: Removing a bad-window notice is not the whole of telling the truth. A
#: reader who looked at one of these charts last week saw different numbers
#: and is owed an explanation for why they changed; without one, a restated
#: series is indistinguishable from an unstable one. A correction nobody is
#: told about erodes the same trust the correction was meant to restore.
#:
#: Repaired 21 Oct 2026: 796 rows across three indices, every stored column,
#: in one transaction. Verified by re-running the reconciliation -- inside
#: the window 0 of 275 rows differ on all three, while the 252 rows at the
#: series start and eight scattered sessions outside it are unchanged to the
#: individual date and value.
#: See docs/finding_2026-10-19_three_indices_wrong_for_13_months.md
HISTORY_REPAIRS: dict[str, dict] = {
    code: {
        "from": "2025-05-01",
        "to": "2026-05-31",
        "repaired_on": "2026-10-21",
        "rows": rows,
        "note": (f"Between May 2025 and May 2026 this series held {held}. "
                 f"It was corrected on 21 October 2026 from the same source "
                 f"that matches this index exactly on either side of that "
                 f"period. Figures shown for those dates before the "
                 f"correction were wrong."),
    }
    for code, held, rows in (
        ("ASX20", "the All Ordinaries rather than the S&P/ASX 20", 266),
        ("AXFJ",  "values that were not index levels", 265),
        ("AXMJ",  "values that were not index levels", 265),
    )
}

SOURCE_CHANGES: dict[str, dict] = {
    "ASX100": {
        "changed_on": "2026-10-13",
        "from_source": "yahoo:^AXTO",
        "to_source": "eodhd:ATOI.INDX",
        "note": ("Data to 2026-05-29 came from Yahoo (^AXTO, which stopped "
                 "returning data); data from 2026-10-13 comes from EODHD "
                 "(ATOI.INDX). Sessions between were never recorded."),
    },
    # Five more, 2026-10-17. Yahoo refused this host from the 17th and the
    # last stored row for each is 2026-10-16, so EODHD continues each series
    # from the first session that had no row -- nothing Yahoo produced is
    # restated.
    #
    # Each mapping was measured at median level 0.00000%, median daily-return
    # 0.00000pp and zero outliers across 1,351 stored sessions back to
    # 2021-05-10. These are continuations of the same series, not
    # substitutions, and that is exactly why they must still be declared:
    # "we changed where this number comes from" is a fact a reader is
    # entitled to, whether or not the number moved.
    **{
        code: {
            "changed_on": "2026-10-17",
            "from_source": f"yahoo:{yahoo}",
            "to_source": f"eodhd:{eodhd}",
            "note": (f"Data to 2026-10-16 came from Yahoo ({yahoo}), which "
                     f"stopped serving this host. Data from 2026-10-17 comes "
                     f"from EODHD ({eodhd}). The two agree exactly across "
                     f"1,351 prior sessions, so the series is continuous."),
        }
        for code, yahoo, eodhd in (
            ("ASX50",  "^AFLI", "AFLI.INDX"),
            ("ASX200", "^AXJO", "AXJO.INDX"),
            ("ASX300", "^AXKO", "AXKO.INDX"),
            ("AXEJ",   "^AXEJ", "AXEJ.INDX"),
            ("AXHJ",   "^AXHJ", "AXHJ.INDX"),
        )
    },
}


def market_now():
    """Current time in the market's timezone."""
    from datetime import datetime                               # noqa: PLC0415
    from zoneinfo import ZoneInfo                               # noqa: PLC0415
    return datetime.now(ZoneInfo(MARKET_TZ))


def last_expected_session(now):
    """The most recent session whose close should already be published.

    `now` is a datetime in MARKET_TZ. Taking a datetime rather than a date is
    the point: whether today's close is expected depends on the hour, and a
    date cannot answer that.

    Weekday-based, not calendar-based -- a calendar threshold either fires
    every weekend or gets loosened until it catches nothing.
    """
    from datetime import timedelta                              # noqa: PLC0415
    today = now.date()
    if today.weekday() < 5 and now.hour >= PUBLICATION_CUTOFF_HOUR:
        return today
    day = today - timedelta(days=1)
    while day.weekday() >= 5:            # 5 = Saturday, 6 = Sunday
        day -= timedelta(days=1)
    return day


def sessions_behind(price_date, now) -> int:
    """Weekdays between a price date and the last expected session.

    Holidays count as sessions here, which is why the threshold allows a few.
    Over-counting slightly is safe; under-counting hides staleness.
    """
    from datetime import timedelta                              # noqa: PLC0415
    if price_date is None:
        return 10 ** 6
    target = last_expected_session(now)
    if price_date >= target:
        return 0
    n, day = 0, price_date
    while day < target:
        day += timedelta(days=1)
        if day.weekday() < 5:
            n += 1
    return n


def freshness_status(price_date, now):
    """None (current) | "delayed" | "stale" | "no_data".

    Never silently "current": the only way to get None is to be level with
    the last expected session.

    A series that has missed even one expected session is marked. Whether its
    figures are also withheld is the separate tolerance question.
    """
    if price_date is None:
        return NO_DATA
    n = sessions_behind(price_date, now)
    if n == 0:
        return None
    return DELAYED if n <= STALE_AFTER_SESSIONS else STALE


def is_stale(price_date, now) -> bool:
    """Stale enough to withhold figures. NOT the same as "not current"."""
    return freshness_status(price_date, now) == STALE


def suppress_if_stale(values: dict, now) -> dict:
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
    status = freshness_status(raw, now)
    if status is None:
        return values
    out = dict(values)
    if status == STALE:
        # Only a stale series has its current-figures withheld. A delayed one
        # is marked and still shown: blanking a page because of a public
        # holiday would make the surface useless and teach people to ignore
        # the marking.
        for field in STALE_SUPPRESSED_FIELDS:
            if field in out:
                out[field] = None
    out["data_status"] = status
    if raw is not None:
        # Meaningless for a series that never published: there is no date to
        # count back from, and 0 would read as "up to date".
        out["sessions_behind"] = sessions_behind(raw, now)
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
    # SOURCE_CHANGES is in the material too. It is served on the index
    # response, so adding a declaration changes what a reader is entitled to
    # see -- and a response cached under the old key would omit it. The same
    # argument the docstring makes for UNVERIFIED_SERIES applies: if it
    # changes what we publish about a series, it changes the key.
    material = (repr(sorted(SOURCE_CHANGES.items()))
                + repr(sorted(KNOWN_BAD_WINDOWS.items()))
                + repr(sorted(HISTORY_REPAIRS.items()))
                + repr(sorted(UNVERIFIED_SERIES.items())) + repr(SUPPRESSED_FIELDS)
                + repr(STALE_SUPPRESSED_FIELDS) + repr(STALE_AFTER_SESSIONS)
                + repr(PUBLICATION_CUTOFF_HOUR) + repr(MARKET_TZ))
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
