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
    material = repr(sorted(UNVERIFIED_SERIES.items())) + repr(SUPPRESSED_FIELDS)
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
