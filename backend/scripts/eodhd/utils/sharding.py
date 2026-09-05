"""
Stable weekly sharding
======================
Fundamentals cost 10 EODHD calls per symbol, so refreshing the whole universe
in one run is ~21,000 calls — most of the 30,000 the ASX Screener is allocated,
and enough to push the dividends and splits jobs behind it into the reserve.

Splitting the universe across four Sundays smooths that to ~5,250 a week while
still giving every company a roughly monthly refresh.

The shard must be stable: a symbol should stay in its group as the universe
gains and loses listings, otherwise companies drift between weeks and some go
months without an update. Python's built-in hash() is salted per process, so it
cannot be used here — md5 of "exchange:ticker" is used instead, for stability
rather than for any security property.
"""
import hashlib
from datetime import date

SHARD_COUNT = 4


def shard_of(code: str, exchange: str = "AU", shards: int = SHARD_COUNT) -> int:
    """Stable shard index for a symbol. Same answer on every run and machine."""
    key = f"{exchange}:{code}".upper().encode()
    return int(hashlib.md5(key).hexdigest(), 16) % shards


def current_shard(today: date | None = None, shards: int = SHARD_COUNT) -> int:
    """
    Shard due this week, from the ISO week number.

    ISO weeks are used rather than a running counter so the schedule is
    reproducible: any date maps to exactly one shard, with no stored state to
    drift if a week is missed.
    """
    d = today or date.today()
    return d.isocalendar()[1] % shards


def filter_to_shard(codes: list[str], shard: int, exchange: str = "AU",
                    shards: int = SHARD_COUNT) -> list[str]:
    """The subset of `codes` belonging to `shard`."""
    return [c for c in codes if shard_of(c, exchange, shards) == shard]
