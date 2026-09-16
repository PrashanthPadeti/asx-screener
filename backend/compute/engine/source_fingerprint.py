"""
What does today's yearly_metrics actually represent?
====================================================
`DAILY_CANONICAL` reuses the `yearly_compute` output from an earlier cycle
rather than recomputing it. That reuse needs a proof, not an age.

    A daily run may reuse market.yearly_metrics only when the current
    fingerprint of yearly_compute's ENTIRE input set equals the fingerprint
    that the successful yearly_compute run proved.

Why not a timestamp
-------------------
`financials.annual_pnl` and its siblings carry ``data_as_of TIMESTAMPTZ
DEFAULT NOW()``, which looks like exactly the lineage marker this needs. It was
rejected on evidence, in both directions:

    Four writers touch financials.annual_*: transform_financials.py,
    load_fundamentals.py, load_eodhd_financials.py and load_fmp_financials.py.
    Only the first sets data_as_of. The other three upsert financially
    consumed values and leave it exactly as it was -- so a real source change
    reads as unchanged, which is the failure that matters.

    And transform_financials sets data_as_of = NOW() on every load whether or
    not a single value changed -- so an unchanged source reads as changed, and
    reuse would be refused for nothing.

A timestamp may be used for this only if it provably moves whenever any
consumed input moves, and only when it does. This one does neither.

What is fingerprinted, and why only this
----------------------------------------
Every table yearly_compute reads, at the projection it actually reads -- read
off the code, not guessed:

    financials.annual_pnl            the driving table
    financials.annual_balance_sheet  LEFT JOIN on (asx_code, fiscal_year)
    financials.annual_cashflow       LEFT JOIN on (asx_code, fiscal_year)
    market.dividends                 LATERAL, for derived DPS and franking
    staging_au.shares_stats          the per-share proxy
    market.daily_prices              per-fiscal-year price metrics

A fingerprint of `annual_pnl` alone would certify stale yearly output after a
balance-sheet correction, which is the whole reason this covers the full set.

The two scoped tables are the subtle part
-----------------------------------------
`market.daily_prices` gains rows every single day. Fingerprinting the whole
table would change daily, reuse would never be valid, and `DAILY_CANONICAL`
would promote itself to the full plan every night -- defeating its purpose.
Ignoring prices entirely would miss a historical price correction, which
genuinely does change yearly metrics.

Neither is necessary, because every price this computation consumes is bounded
above by the fiscal year end:

    price_at(prices, ped)            close at or before period_end_date
    price_window(prices, ped)        the 12 months ENDING at period_end_date
    price_return(prices, ped, n)     n years ENDING at period_end_date
    price_at_compute                 the price AT period_end_date, not today's

So the projection is prices up to each company's latest `period_end_date`.
Today's bar cannot change any yearly metric, and a backfill of historical
prices can -- and the fingerprint reflects exactly that. `market.dividends` is
bounded the same way: the LATERAL reads ex_dates at or before the year end.

When a new fiscal year lands, the bound moves forward, the price projection
widens and the fingerprint changes. It should: the yearly output genuinely
needs recomputing.

Determinism
-----------
Each row is projected to text with explicit NULL encoding and trimmed numeric
scale, so NUMERIC '1.50' and '1.5' -- equal numbers, different text -- do not
read as a source change. Rows are hashed individually and combined in hash
order, so the digest never depends on the order PostgreSQL happened to return.
Ingestion metadata is deliberately absent: hashing it would invalidate reuse
when nothing financially meaningful changed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Optional

#: Bump when a projection changes. A fingerprint computed under one version is
#: not comparable with one computed under another: the digest would differ for
#: a reason that has nothing to do with the data, and reuse would be refused --
#: or, far worse if a projection ever narrows, wrongly permitted. The version
#: is part of the aggregate, so a mismatch is visible rather than mysterious.
FINGERPRINT_SCHEMA_VERSION = 1

#: Field separator inside a row projection. A unit separator cannot occur in a
#: code, a date or a rendered number, so two different rows can never render
#: to the same string.
FIELD_SEP = r"\x1f"

#: NULL, distinguishably. Rendering it as the empty string would make a NULL
#: revenue and a revenue of '' the same member, and "cannot exist" and
#: "happens to be absent" are different financial states.
NULL_TOKEN = r"\\N"


def _text(expr: str, is_numeric: bool) -> str:
    """One column, rendered deterministically.

    trim_scale removes trailing zeros, so NUMERIC(18,2) '1.50' and
    NUMERIC(18,6) '1.500000' -- the same number stored at different scales,
    which is exactly what happens when four different loaders write the same
    table -- produce the same text and do not read as a source change.

    Numeric-ness is resolved from information_schema rather than inline with
    pg_typeof: a CASE would have to type-check `trim_scale(asx_code::numeric)`
    on the branch it never takes, which is the kind of construct that works
    until the day it does not.
    """
    rendered = f"trim_scale({expr})::text" if is_numeric else f"{expr}::text"
    return f"coalesce({rendered}, '{NULL_TOKEN}')"


def _numeric_columns(cur, table: str) -> set:
    """Which of this table's columns are NUMERIC.

    Only NUMERIC gets trim_scale. float8/real are already rendered by
    PostgreSQL in shortest-round-trip form, which is deterministic, and casting
    them through numeric to tidy them would lose precision -- changing the
    fingerprint for a reason that is not a source change.
    """
    schema, name = table.split(".", 1)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_schema = %s AND table_name = %s
           AND data_type = 'numeric';""", (schema, name))
    return {r[0] for r in cur.fetchall()}


def _row_hash(columns: list[str], numeric: set) -> str:
    joined = f" || '{FIELD_SEP}' || ".join(
        _text(c, c in numeric) for c in columns)
    return f"md5({joined})"


def _table_digest_sql(table: str, columns: list[str], where: str = "",
                      numeric: set = frozenset()) -> str:
    """A digest of one table's consumed projection.

    Combined in hash order rather than key order: the result is identical
    either way, and ordering by the row hash needs no separate sort expression
    per table, so a table added later cannot be given the wrong sort key.
    """
    # The marker names the table this digest is OF. The two scoped projections
    # carry a correlated subquery over financials.annual_pnl, so the statement
    # text alone contains more than one table name and nothing in it says which
    # is the subject -- in a log, in pg_stat_statements, or to anything reading
    # these queries back.
    return f"""
        /* fingerprint:{table} */
        SELECT count(*) AS n,
               coalesce(md5(string_agg(h, '' ORDER BY h)), 'empty') AS digest
          FROM (SELECT {_row_hash(columns, numeric)} AS h
                  FROM {table} {where}) s
    """


#: The bound both scoped tables share: a company's latest fiscal year end.
#: Expressed against the driving table, because that is where the computation
#: takes it from.
_LATEST_PERIOD_END = """
    (SELECT max(p2.period_end_date) FROM financials.annual_pnl p2
      WHERE p2.asx_code = {alias}.asx_code)
"""

#: Exactly the columns fetch_financials, fetch_current_shares and
#: fetch_all_prices select. Tested against yearly_compute's own source, so a
#: column added to the computation without being added here fails loudly
#: rather than silently narrowing what "current" means.
PROJECTIONS: dict[str, tuple[list[str], str]] = {
    "financials.annual_pnl": ([
        "asx_code", "fiscal_year", "period_end_date",
        "revenue", "gross_profit", "ebitda", "ebit", "interest_expense",
        "net_profit", "eps", "eps_diluted", "dps", "dps_franking_pct",
        "gpm", "opm", "npm", "ebitda_margin",
    ], ""),

    "financials.annual_balance_sheet": ([
        "asx_code", "fiscal_year",
        "total_assets", "total_equity",
        "total_current_assets", "total_current_liab",
        "total_debt", "net_debt", "cash_equivalents", "long_term_debt",
        "retained_earnings", "working_capital",
        "book_value_per_share", "shares_outstanding",
        "trade_receivables", "inventory",
    ], ""),

    "financials.annual_cashflow": ([
        "asx_code", "fiscal_year",
        "cfo", "capex", "fcf", "equity_raised", "cfi", "dividends_paid",
    ], ""),

    "market.dividends": ([
        "asx_code", "ex_date", "amount_per_share", "franking_pct",
        "dividend_type",
    ], "WHERE ex_date <= " + _LATEST_PERIOD_END.format(alias="market.dividends")),

    "staging_au.shares_stats": (["asx_code", "shares_outstanding"], ""),

    "market.daily_prices": ([
        "asx_code",
        "DATE(time AT TIME ZONE 'Australia/Sydney')",
        "close",
    ], "WHERE DATE(time AT TIME ZONE 'Australia/Sydney') <= "
       + _LATEST_PERIOD_END.format(alias="market.daily_prices")),
}


@dataclass(frozen=True)
class SourceFingerprint:
    """What yearly_compute's inputs looked like, as content rather than time."""

    schema_version: int
    tables: Mapping[str, dict]          # table -> {"n": int, "digest": str}
    aggregate: str

    def to_json(self) -> dict:
        return {"schema_version": self.schema_version,
                "tables": {k: dict(v) for k, v in sorted(self.tables.items())},
                "aggregate": self.aggregate}

    @classmethod
    def from_json(cls, blob) -> Optional["SourceFingerprint"]:
        if not blob:
            return None
        if isinstance(blob, str):
            blob = json.loads(blob)
        return cls(schema_version=blob["schema_version"],
                   tables=blob["tables"], aggregate=blob["aggregate"])

    def differences(self, other: "SourceFingerprint") -> list[str]:
        """Which tables moved. The aggregate says whether; this says where.

        A precondition failure that only reports 'the fingerprint changed'
        leaves the operator to guess whether a balance-sheet correction landed
        or a price backfill ran.
        """
        if self.schema_version != other.schema_version:
            return [f"fingerprint schema {other.schema_version} → "
                    f"{self.schema_version} (not comparable)"]
        out = []
        for name in sorted(set(self.tables) | set(other.tables)):
            a, b = self.tables.get(name), other.tables.get(name)
            if a == b:
                continue
            if a is None or b is None:
                out.append(f"{name}: present in only one fingerprint")
            elif a["digest"] != b["digest"]:
                out.append(f"{name}: {b['n']:,} → {a['n']:,} rows, content "
                           f"changed")
        return out


def aggregate_digest(schema_version: int, tables: Mapping[str, dict]) -> str:
    """One value to compare. Order-independent and version-tagged."""
    payload = json.dumps(
        {"v": schema_version,
         "t": {k: [v["n"], v["digest"]] for k, v in sorted(tables.items())}},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute(cur) -> SourceFingerprint:
    """Measure yearly_compute's entire input set, as it currently stands."""
    tables = {}
    for table, (columns, where) in PROJECTIONS.items():
        numeric = _numeric_columns(cur, table)
        cur.execute(_table_digest_sql(table, columns, where, numeric))
        n, digest = cur.fetchone()
        tables[table] = {"n": int(n), "digest": digest}
    return SourceFingerprint(
        schema_version=FINGERPRINT_SCHEMA_VERSION,
        tables=tables,
        aggregate=aggregate_digest(FINGERPRINT_SCHEMA_VERSION, tables))


#: Where the proven fingerprint lives on yearly_compute's stage evidence.
STAGE_DETAIL_KEY = "yearly_source_fingerprint"


def proven_by_latest_yearly(cur) -> tuple[Optional[int], Optional[SourceFingerprint]]:
    """The fingerprint the most recent SUCCESSFUL yearly_compute proved.

    Asks for the positive record. A run whose yearly_compute failed, or never
    ran, has no row here and therefore grants no reuse -- the same rule that
    governs publication, applied to the thing publication would be built on.
    """
    cur.execute(f"""
        SELECT run_id, details -> '{STAGE_DETAIL_KEY}'
          FROM screener.compute_run_stages
         WHERE stage_name = 'yearly_compute' AND status = 'success'
           AND details ? '{STAGE_DETAIL_KEY}'
         ORDER BY run_id DESC
         LIMIT 1;""")
    row = cur.fetchone()
    if not row:
        return None, None
    return row[0], SourceFingerprint.from_json(row[1])
