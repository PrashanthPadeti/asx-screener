"""
A price from a retired source can never become current
=======================================================
The yfinance backfill was deleted on 30 Sep 2026. Deleting the job stopped
acquisition; it did not stop SERVING. 1,849 rows remain in
market.daily_prices, and on 1 Oct four instruments -- DVDY, MTN, XASG
(ETFs) and HGODB (a deferred-settlement line) -- still had them as their
NEWEST price, 33 and 23 trading sessions after the market moved on.

What this rule is NOT
---------------------
It is not a staleness threshold, and it asserts nothing about trading
activity. Measured on 1 Oct, the staleness tail is continuous --
0, 1, 2, 3, 4, 5, 6, 8, 11 ... 42, 46, 47, 72, 74, 91, 105 sessions behind
-- with no natural cut-off anywhere in it. And this system has no suspension
signal at all:

    market.companies.status   separates only active from delisted
    EODHD General             carries no status field for these codes
    market.asx_announcements  covers 216 of 2,155 codes, and NONE of the
                              nineteen stale ones

So "has not traded" and "was not collected" are indistinguishable here. NRZ
last traded 105 sessions ago and reads `active`; it is probably suspended,
and suppressing it would assert a feed failure nobody has established.

What it IS
----------
A narrower and provable claim: a price from a source we have retired can
never become current, by any mechanism, because nothing will ever write
another one. That needs no threshold and makes no judgement about the
instrument.

Storage is untouched. The history stays in market.daily_prices -- the same
storage-versus-serving distinction P0-A uses everywhere else. Only
eligibility changes, and it changes by the price becoming absent rather than
by a new clause in serving_predicate.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_retired_price_source.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.serving_population import (                    # noqa: E402
    RETIRED_PRICE_SOURCES, current_source_predicate, serving_predicate,
)

BUILDER = BACKEND / "scripts/eodhd/v2/build_screener_universe.py"


def _universe_sql() -> str:
    src = BUILDER.read_text(encoding="utf-8")
    return re.search(r'UPSERT_SQL = """(.*?)"""', src, re.S).group(1)


def test_the_retired_source_is_declared_not_inlined():
    assert "yahoo" in RETIRED_PRICE_SOURCES
    assert current_source_predicate().count("yahoo") == 1


def test_the_predicate_excludes_only_retired_sources():
    p = current_source_predicate()
    assert "NOT IN" in p and "'yahoo'" in p
    assert "eodhd" not in p, "the rule must name what is retired, not what is kept"


def test_a_null_data_source_is_treated_as_retired_safe():
    """COALESCE, so a row with no source recorded is not silently admitted by
    a NULL comparison that evaluates to UNKNOWN."""
    assert current_source_predicate().startswith("COALESCE(")


def test_every_price_lateral_is_gated():
    """Three laterals read market.daily_prices: the latest price, the 52-week
    range and the 20-day average volume.

    Gating only the first would exclude an instrument from serving while its
    52-week range still carried retired data -- the same defect one level
    down, and harder to see.
    """
    sql = _universe_sql()
    assert sql.count("FROM market.daily_prices") == 3, (
        "a lateral was added or removed; check it is gated too")
    assert sql.count("{current_source}") == 3


def test_the_sql_renders_with_the_shared_predicate():
    rendered = _universe_sql().format(code_filter="",
                                      current_source=current_source_predicate())
    assert rendered.count("NOT IN ('yahoo')") == 3


def test_the_builder_uses_the_shared_definition_not_a_literal():
    """A hard-coded `data_source <> 'yahoo'` in the SQL would pass every test
    above while drifting from the declared list the moment a second source is
    retired."""
    src = BUILDER.read_text(encoding="utf-8")
    assert "current_source_predicate" in src
    sql = _universe_sql()
    assert "'yahoo'" not in sql, "the retired source is hard-coded in the SQL"


def test_serving_predicate_is_unchanged():
    """The contract is not widened. An instrument whose only prices come from
    a retired source simply has no price, and `price IS NOT NULL` already
    excludes it -- so no frozen contract moves to accommodate this.
    """
    assert serving_predicate() == "status = 'active' AND price IS NOT NULL"


def test_the_rule_is_not_a_staleness_threshold():
    """Stated as a test because the distinction is the whole justification.
    A date or session comparison here would be the semantic invention this
    deliberately avoids."""
    src = (BACKEND / "compute/engine/serving_population.py").read_text(
        encoding="utf-8")
    body = src[src.index("def current_source_predicate"):
               src.index("#: Instrument types")]
    for forbidden in ("CURRENT_DATE", "NOW()", "INTERVAL", "price_date",
                      "sessions"):
        assert forbidden not in body, (
            f"{forbidden} in the predicate: this is a source rule, not a "
            f"staleness rule")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
