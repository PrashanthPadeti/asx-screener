"""The FROM block as evidence: every source, its alias, its row-selection rule.

The user's acceptance points for this layer are mostly per-SOURCE, not
per-column: join keys, date conditions, evidence of cardinality, source
period and freshness. A lateral with `ORDER BY period_end_date DESC LIMIT 1`
answers "which period does this column's value come from" for every column
that reads its alias, and answers it once.

Cardinality is the load-bearing claim. One row per asx_code in the output
requires that every join contributes at most one row per driving row:
  * a plain join on the other side's primary key   -> at most one
  * a lateral with LIMIT 1                         -> at most one
  * an aggregate with no GROUP BY                  -> exactly one
Anything else fans out, and a fan-out in this statement silently multiplies
rows in the universe.
"""
import json
import re
import sys
from pathlib import Path

EV = Path("database/stm/evidence")
EV.mkdir(parents=True, exist_ok=True)
SP = Path(sys.argv[1]) if len(sys.argv) > 1 else EV
BUILDER = Path("backend/scripts/eodhd/v2/build_screener_universe.py")

pairs = json.loads((SP / "universe_pairs.json").read_text(encoding="utf-8"))
lines = BUILDER.read_text(encoding="utf-8").splitlines()
start, end = pairs["from_line"] - 1, pairs["conflict_line"] - 1

# The line numbers come from another generator's CACHED output, and the file
# they index has been edited since that output was written every time this
# matters. On 13 Nov 2026 a stale universe_pairs.json pointed this parser at
# a window that ended three laterals early: it reported 30 sources instead of
# 32, invented one with alias None out of the truncated tail, and the
# cardinality guard that consumes this file passed on all seven assertions.
# A wrong answer, silently, from an input that looked fine.
#
# So the anchors are CHECKED against the file rather than trusted. This is
# not a style preference: a derived artifact that indexes another artifact by
# position must verify the position still means what it meant, or it reports
# on a file that no longer exists.
_from_anchor = lines[start].strip() if 0 <= start < len(lines) else ""
_conflict_anchor = lines[end].strip() if 0 <= end < len(lines) else ""
if not re.match(r"^FROM\s", _from_anchor, re.I) or \
        not re.search(r"ON\s+CONFLICT", _conflict_anchor, re.I):
    raise SystemExit(
        f"universe_pairs.json is stale: it says the FROM block runs from "
        f"line {pairs['from_line']} to {pairs['conflict_line']}, but those "
        f"lines now read\n"
        f"  {pairs['from_line']}: {_from_anchor!r}\n"
        f"  {pairs['conflict_line']}: {_conflict_anchor!r}\n"
        f"Run `python backend/scripts/stm/universe_pairs.py` first. "
        f"Parsing from here would describe a statement that is not the one "
        f"in the file.")


def strip(s):
    return re.sub(r"--.*$", "", s)


block = [strip(ln) for ln in lines[start:end]]

sources, i, depth = [], 0, 0
while i < len(block):
    line = block[i]
    s = line.strip()

    m = re.match(r"^(?:FROM|(LEFT|INNER|CROSS)?\s*JOIN)\s+LATERAL\s*\($", s, re.I)
    if m or re.match(r"^(?:LEFT\s+)?JOIN\s+LATERAL\s*\($", s, re.I):
        # Consume the lateral subquery to its matching close paren, which
        # carries the alias on the same line.
        d, body = 1, []
        j = i + 1
        while j < len(block) and d > 0:
            for ch in block[j]:
                if ch == "(":
                    d += 1
                elif ch == ")":
                    d -= 1
                    if d == 0:
                        break
            if d > 0:
                body.append(block[j])
            j += 1
        closing = block[j - 1].strip()
        alias = None
        am = re.match(r"^\)\s*([a-z][a-z0-9_]*)", closing, re.I)
        if am:
            alias = am.group(1)
        text = " ".join(x.strip() for x in body)
        base = re.findall(r"\bFROM\s+([a-z_]+\.[a-z_]+)", text, re.I)
        has_limit = bool(re.search(r"\bLIMIT\s+1\b", text, re.I))
        has_group = bool(re.search(r"\bGROUP\s+BY\b", text, re.I))
        aggregate = bool(re.search(
            r"\b(count|sum|avg|min|max|array_agg|bool_or|bool_and)\s*\(",
            text, re.I))
        order = re.findall(r"\bORDER\s+BY\s+([^)]{0,80}?)(?:\s+LIMIT|\s*$)",
                           text, re.I)
        where = re.findall(r"\bWHERE\s+(.{0,160})", text, re.I)
        # Columns this lateral constrains by equality, local side only.
        #
        # A LIMIT 1 with no ORDER BY is still deterministic when these cover
        # a unique key of the base table: the WHERE picks the row and LIMIT 1
        # is a guard against a duplicate that should not exist. Without them,
        # LIMIT 1 yields one ARBITRARY row, which is a different defect from
        # a fan-out and invisible in the output.
        wtext = ""
        wm = re.search(r"\bWHERE\b(.*?)(?=\bORDER\s+BY\b|\bLIMIT\b|$)",
                       text, re.I | re.S)
        if wm:
            wtext = wm.group(1)
        eq_columns = sorted({
            m.group(1).lower() for m in
            re.finditer(r"(?:^|\bAND\b)\s*([a-z_][a-z0-9_]*)\s*=",
                        wtext, re.I)})
        # What the lateral PRODUCES, not only what it reads.
        #
        # The evidence recorded base tables, ordering, cardinality and the
        # WHERE -- everything about how a lateral selects its row, and
        # nothing about what it hands back. That blind spot is why no guard
        # could ask the question finding 13 turned on: does this lateral
        # compute a quantity a joined producer already publishes?
        #
        # dp52 produced `high_52w` and `low_52w`, names that
        # market.daily_metrics already carries, from a raw price table with
        # no coverage rule. The evidence said it read market.daily_prices
        # and returned at most one row, both true, and had no way to say it
        # was a second definition of something the statement already had.
        outputs = sorted({
            m.group(1).lower() for m in
            re.finditer(r"\bAS\s+([a-z_][a-z0-9_]*)", text, re.I)})
        sources.append({
            "kind": "lateral",
            "alias": alias,
            "base_tables": base,
            "outputs": outputs,
            "limit_1": has_limit,
            "group_by": has_group,
            "aggregate_no_group": aggregate and not has_group,
            "order_by": order[:1],
            "where": where[:1],
            "eq_columns": eq_columns,
            "at_most_one_row": has_limit or (aggregate and not has_group),
        })
        i = j
        continue

    m = re.match(r"^(FROM|(?:LEFT\s+|INNER\s+|CROSS\s+)?JOIN)\s+"
                 r"([a-z_]+\.[a-z_]+)\s+(?:AS\s+)?([a-z][a-z0-9_]*)",
                 s, re.I)
    if m:
        on = []
        for k in range(i, min(i + 4, len(block))):
            om = re.search(r"\bON\s+(.{0,160})", block[k], re.I)
            if om:
                on.append(om.group(1).strip())
                break
        sources.append({
            "kind": m.group(1).upper().strip(),
            "alias": m.group(3),
            "base_tables": [m.group(2)],
            "on": on[:1],
            "limit_1": False,
            "at_most_one_row": None,   # decided by the key the ON names
        })
    i += 1

fanout = [s for s in sources if s["kind"] == "lateral"
          and not s["at_most_one_row"]]

(SP / "universe_joins.json").write_text(
    json.dumps({"sources": sources}, indent=1), encoding="utf-8")

lat = [s for s in sources if s["kind"] == "lateral"]
print(f"{len(sources)} sources: {len(lat)} laterals, "
      f"{len(sources) - len(lat)} plain")
print(f"  laterals with LIMIT 1          "
      f"{sum(1 for s in lat if s['limit_1'])}")
print(f"  laterals aggregating, no GROUP "
      f"{sum(1 for s in lat if s.get('aggregate_no_group'))}")
print(f"  laterals that could FAN OUT    {len(fanout)}")
for s in fanout:
    print(f"     {s['alias']}  {s['base_tables']}")
print()
for s in sources:
    if s["kind"] != "lateral":
        print(f"  {s['kind']:10} {s['alias']:6} {s['base_tables'][0]:40} "
              f"ON {(s.get('on') or [''])[0][:70]}")
