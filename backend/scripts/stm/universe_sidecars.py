"""Emit the Gold -> Universe mapping sidecars.

Why this is generated and the other layers' sidecars are hand-written
--------------------------------------------------------------------
`screener.universe` is one statement. 341 of its 376 columns are a single
SELECT expression in a known position, 33 sources carry one row-selection
rule each, and 80 columns are overwritten afterwards by a writer whose
column list comes from a registry. Typing that out 341 times would be
copying evidence by hand into a file that is then free to disagree with it.

So the mechanical half is emitted from database/stm/evidence/:

    derivation_formula   the SELECT expression, verbatim
    source_table         resolved from the expression's alias
    source_column        the column named on the source side
    join_condition       that source's row-selection rule
    writer_job           every writer of the column, in precedence order

and the authored half lives here, in prose, at the level where it is
actually true. Columns inside one of the builder's own SELECT sections share
their source, grain, unit, freshness and adjustment basis -- so that prose is
written once per section, and a column states only what makes it different.
Repeating a section's rule into forty columns would read as forty reviewed
claims when it is one.

Drift is a test, not a hope: test_universe_sidecars_match_the_statement
re-derives the mechanical fields and fails when the YAML disagrees.

Usage:
    python backend/scripts/stm/universe_sidecars.py        # from repo root
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

EV = Path("database/stm/evidence")
OUT = Path("database/stm/mappings")
TABLE = "screener.universe"

#: Which output file each of the builder's 42 SELECT sections lands in.
#: Grouped by subject so a reader opens one file per question, not 42.
FILES: dict[str, tuple[str, ...]] = {
    "screener_universe_identity": (
        "Identity",
        "Market cap tier flags (derived from vs.market_cap, raw AUD)",
        "Admin tags (from market.companies)",
    ),
    "screener_universe_price": (
        "Price (latest close + 52w range)",
        "Volatility & risk",
        "Technicals: the daily source, or nothing",
        "Volume signals (daily_metrics)",
        "Tier 2: daily signals (from daily_metrics)",
    ),
    "screener_universe_returns": (
        "Returns (daily -> weekly/monthly fallback)",
        "Multi-year returns, from daily_metrics as of v11.2.63",
    ),
    "screener_universe_valuation": (
        "Valuation ratios",
        "Dividends",
        "Per-share & working capital",
    ),
    "screener_universe_fundamentals": (
        "Profitability TTM",
        "EPS",
        "Income Statement FY0 / FY1",
        "Balance Sheet",
        "Cash Flow",
        "Income statement history (annual levels, AUD millions)",
        "Income-statement & balance-sheet line items (annual, AUD millions)",
        "Derived ratios (from the line items above)",
    ),
    "screener_universe_growth": (
        "Growth rates",
        "Growth rates (decimal ratios; YoY = (end-base)/|base|, CAGR needs both > 0)",
        "Multi-year quality & CAGR (from yearly_metrics - latest FY)",
        "Latest-quarter YoY growth (from quarterly_metrics)",
        "Half-yearly HoH growth (from halfyearly_metrics - latest half)",
    ),
    "screener_universe_signals": (
        "Quick-win metrics (from yearly_metrics + daily_metrics)",
        "Partial metrics",
        "Quick wins",
        "Profit-based signals",
        "Sales-based signals",
        "Balance sheet signals",
        "Tier-1 qualitative proxies",
        "Ratio framework signals",
        "Cash flow signals",
        "Quality proxy scores (from yearly_metrics)",
        "Tier 3: EODHD data previously unused",
    ),
    "screener_universe_market_structure": (
        "Analyst",
        "Analyst-derived (computed from existing buy/sell/hold counts)",
        "Short interest (ASIC - latest report date per stock)",
        "Shares & Ownership",
        "Tier 2: ASX announcements signals (market.asx_announcements)",
    ),
}


def load(name: str) -> dict:
    path = EV / f"{name}.json"
    if not path.exists():
        raise SystemExit(
            f"2  {path} is missing. Run the four evidence scripts in "
            f"backend/scripts/stm/ first -- authoring the mechanical half by "
            f"hand is the thing this script exists to avoid.")
    return json.loads(path.read_text(encoding="utf-8"))


def normalise_section(name: str) -> str:
    """Section headers carry box-drawing and arrow characters.

    Matched on an ASCII-folded form so the FILES table above stays typeable
    and a stray dash in the SQL comment does not orphan a whole section.
    """
    return (name.replace("→", "->").replace("—", "-")
                .replace("–", "-").strip())


def source_of(expr: str, aliases: dict[str, str]) -> tuple[str, str]:
    """(source_table, source_column) for an expression, or ("", "").

    Multi-source expressions report every alias they touch; a single
    `alias.column` reference also yields the column. A literal or a pure
    computation over other output columns yields neither, which is correct
    and is not the same as unknown.
    """
    refs = re.findall(r"\b([a-z][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", expr)
    seen_tables, cols = [], []
    for alias, col in refs:
        table = aliases.get(alias)
        if not table:
            continue
        if table not in seen_tables:
            seen_tables.append(table)
        ref = f"{table}.{col}"
        if ref not in cols:
            cols.append(ref)
    return "; ".join(seen_tables), "; ".join(cols)


def join_rule(source: dict) -> str:
    """One source's row-selection rule, in the terms the statement uses."""
    base = "; ".join(source["base_tables"]) or "(unresolved)"
    if source["kind"] != "lateral":
        on = (source.get("on") or [""])[0]
        return f"{source['kind']} {base} AS {source['alias']} ON {on}".strip()

    order = (source.get("order_by") or [""])[0].strip()
    where = (source.get("where") or [""])[0].strip()
    if source.get("aggregate_no_group"):
        shape = "aggregate, no GROUP BY -> exactly one row"
    elif order:
        shape = f"ORDER BY {order} LIMIT 1 -> the named row"
    elif source.get("eq_columns"):
        shape = (f"WHERE equality on {', '.join(source['eq_columns'])} "
                 f"(a unique key) LIMIT 1 -> the determined row")
    else:
        shape = "LIMIT 1 with no ORDER BY -> ONE ARBITRARY ROW"
    return (f"LEFT JOIN LATERAL ({base}) AS {source['alias']}: {shape}"
            + (f"; WHERE {where}" if where else ""))


def aliases_used(expr: str, aliases: dict[str, str]) -> list[str]:
    out = []
    for alias in re.findall(r"\b([a-z][a-z0-9_]*)\.", expr):
        if alias in aliases and alias not in out:
            out.append(alias)
    return out


def build() -> int:
    pairs = load("universe_pairs")
    joins = load("universe_joins")
    attrib = load("universe_attrib")
    sections = load("universe_sections")

    expr = {c["column"]: c["expr"] for c in pairs["columns"]}
    attr = {r["column"]: r for r in attrib["columns"]}
    by_alias = {s["alias"]: s for s in joins["sources"] if s["alias"]}
    alias_table = {s["alias"]: (s["base_tables"][0] if s["base_tables"] else "")
                   for s in joins["sources"] if s["alias"]}

    section_of = {col: normalise_section(name)
                  for col, name in sections["section_of"].items()}

    # Every section must land in exactly one file, or a column silently
    # vanishes from the document while the coverage report still counts it.
    placed = {normalise_section(s) for group in FILES.values() for s in group}
    present = set(section_of.values())
    orphans = sorted(present - placed)
    phantom = sorted(placed - present)
    if orphans or phantom:
        raise SystemExit(
            f"2  section routing does not match the statement.\n"
            f"   sections with no output file: {orphans}\n"
            f"   output files naming no section: {phantom}\n"
            f"   A section with no file is columns missing from the document.")

    from universe_prose import COLUMN_PROSE, SECTION_PROSE  # noqa: E402

    missing_prose = sorted(present - set(map(normalise_section, SECTION_PROSE)))
    if missing_prose:
        raise SystemExit(
            f"2  no authored prose for sections: {missing_prose}. An emitted "
            f"row with mechanical fields and no business rule reads as "
            f"reviewed when nobody reviewed it.")
    prose_by_section = {normalise_section(k): v
                        for k, v in SECTION_PROSE.items()}

    written = 0
    for filename, section_names in FILES.items():
        wanted = {normalise_section(s) for s in section_names}
        columns: dict[str, dict] = {}

        for column, section in sorted(section_of.items(),
                                      key=lambda kv: attr[kv[0]]["ordinal"]):
            if section not in wanted:
                continue
            e = expr[column]
            table, source_col = source_of(e, alias_table)
            rules = [join_rule(by_alias[a]) for a in aliases_used(e, alias_table)
                     if a in by_alias]

            row = dict(prose_by_section[section])
            row.update({
                "derivation_formula": " ".join(e.split()),
                "source_table": table,
                "source_column": source_col,
                "tables_involved": table,
                "join_condition": " | ".join(rules),
                "writer_job": "; ".join(attr[column]["writers"]),
            })
            row.update(COLUMN_PROSE.get(column, {}))
            columns[column] = row

        if not columns:
            raise SystemExit(f"2  {filename} would be empty")

        doc = {"columns": {TABLE: columns}}
        path = OUT / f"{filename}.yaml"
        header = (
            f"# {TABLE} -- {', '.join(section_names)}\n"
            f"# GENERATED by backend/scripts/stm/universe_sidecars.py.\n"
            f"# Prose is authored in backend/scripts/stm/universe_prose.py;\n"
            f"# the mechanical fields are re-derived and checked by\n"
            f"# backend/tests/test_universe_sidecars_match_the_statement.py.\n"
            f"# Edit the prose module, not this file.\n")
        path.write_text(
            header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                    width=100, default_flow_style=False),
            encoding="utf-8")
        print(f"  {path.name:46} {len(columns):4} columns")
        written += len(columns)

    print(f"{written} columns emitted across {len(FILES)} files")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(build())
