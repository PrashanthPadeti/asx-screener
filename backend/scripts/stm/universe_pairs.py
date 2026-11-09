"""Pair every INSERT column of screener.universe with its SELECT expression.

Position is the only thing that binds the two lists, so the pairing is done
by walking the SELECT at depth 0 and splitting on top-level commas -- the
same rule PostgreSQL applies. A naive comma split would make COALESCE(a, b)
two expressions and silently shift every pair after it.

Output is JSON: {"columns": [{"ordinal", "column", "expr", "alias_line"}],
"alias_tables": {...}} so the authoring step reads evidence, not my memory.
"""
import json
import re
import sys
from pathlib import Path

BUILDER = Path("backend/scripts/eodhd/v2/build_screener_universe.py")
EV = Path("database/stm/evidence")
EV.mkdir(parents=True, exist_ok=True)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else EV / "universe_pairs.json"

lines = BUILDER.read_text(encoding="utf-8").splitlines()


def strip(line):
    return re.sub(r"--.*$", "", line)


start = next(i for i, ln in enumerate(lines)
             if "INSERT INTO screener.universe (" in ln)
end = next(i for i in range(start + 1, len(lines))
           if strip(lines[i]).strip() == ")")
body = " ".join(strip(ln).strip() for ln in lines[start + 1:end])
columns = [c.strip() for c in body.split(",") if c.strip()]

select = next(i for i in range(start, len(lines))
              if strip(lines[i]).strip() == "SELECT")

# Walk from after SELECT to the top-level FROM, splitting on depth-0 commas.
depth = 0
exprs, cur = [], []
from_line = None
for i in range(select + 1, len(lines)):
    s = strip(lines[i])
    if depth == 0 and re.match(r"^FROM\b", s.strip()):
        from_line = i
        break
    buf = ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            cur.append(buf)
            exprs.append(" ".join(x.strip() for x in cur if x.strip()))
            cur, buf = [], ""
            continue
        buf += ch
    cur.append(buf)
if cur:
    exprs.append(" ".join(x.strip() for x in cur if x.strip()))
if from_line is None:
    raise SystemExit("no top-level FROM")

assert len(columns) == len(exprs), f"{len(columns)} cols vs {len(exprs)} exprs"

# The FROM/JOIN block: alias -> table, so an expression's `dm.` prefix
# resolves to a real table instead of being guessed.
tail = []
d = 0
for i in range(from_line, len(lines)):
    s = strip(lines[i])
    tail.append(s)
    if "ON CONFLICT" in s:
        break
from_text = "\n".join(tail)

SQL_WORDS = {"where", "on", "left", "join", "inner", "cross", "lateral",
             "order", "group", "limit", "and", "or", "as", "union", "select"}
alias = {}
for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+(?:LATERAL\s+)?([a-z_]+\.[a-z_]+)\s+"
        r"(?:AS\s+)?([a-z][a-z0-9_]*)",
        from_text, re.I):
    name = m.group(2).lower()
    if name in SQL_WORDS:
        continue
    alias.setdefault(name, m.group(1))

# The `) alias ON TRUE` form: a lateral's alias sits after its closing paren,
# and the subquery inside names its own base table.
laterals = re.findall(r"LEFT JOIN LATERAL \(", from_text)

# DO UPDATE SET list -- which columns the upsert path overwrites. A blank or
# comment-only line does NOT end the list: the real terminator is the closing
# triple quote, and breaking on blank truncated this to zero columns.
conflict_at = next(i for i in range(from_line, len(lines))
                   if "ON CONFLICT" in lines[i])
set_cols = []
for i in range(conflict_at + 1, len(lines)):
    raw = lines[i].strip()
    if raw.startswith('"""') or raw.endswith('"""'):
        break
    s = strip(lines[i])
    m = re.match(r"^\s*([a-z_][a-z0-9_]*)\s*=", s)
    if m:
        set_cols.append(m.group(1))

OUT.write_text(json.dumps({
    "insert_line": start + 1,
    "select_line": select + 1,
    "from_line": from_line + 1,
    "conflict_line": conflict_at + 1,
    "alias_tables": alias,
    "lateral_count": len(laterals),
    "do_update_set": set_cols,
    "columns": [{"ordinal": n + 1, "column": c, "expr": e}
                for n, (c, e) in enumerate(zip(columns, exprs))],
}, indent=1), encoding="utf-8")

print(f"{len(columns)} columns paired; insert@{start+1} select@{select+1} "
      f"from@{from_line+1} conflict@{conflict_at+1}")
print(f"{len(alias)} aliases; {len(set_cols)} DO UPDATE SET columns")
