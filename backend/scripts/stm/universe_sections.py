"""Group the 341 paired columns by the builder's own SELECT section headers.

The grouping is the code's, not mine: each `-- ── Name ──` comment opens a
section and every expression after it belongs to that section until the next.
Authoring in these groups means the document's structure matches the
statement a reader will go and check it against.
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
attrib = json.loads((SP / "universe_attrib.json").read_text(encoding="utf-8"))
by_col = {r["column"]: r for r in attrib["columns"]}

lines = BUILDER.read_text(encoding="utf-8").splitlines()
select_at = pairs["select_line"]
from_at = pairs["from_line"]

HEADER = re.compile(r"--\s*──\s*(.*?)\s*─*\s*$")

# Walk the SELECT body once, tracking the current section and consuming one
# paired column each time a top-level expression ends. The pairing order is
# the statement order, so an index into pairs["columns"] advances in step.
section_of, current, idx = {}, "(before any header)", 0
depth = 0
cols = pairs["columns"]
for i in range(select_at, from_at - 1):
    raw = lines[i]
    h = HEADER.search(raw)
    if h and raw.strip().startswith("--"):
        current = h.group(1).strip()
        continue
    s = re.sub(r"--.*$", "", raw)
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            if idx < len(cols):
                section_of.setdefault(cols[idx]["column"], current)
                idx += 1
# the final expression carries no trailing comma
if idx < len(cols):
    section_of.setdefault(cols[idx]["column"], current)
    idx += 1

missing = [c["column"] for c in cols if c["column"] not in section_of]
if missing:
    sys.exit(f"2  {len(missing)} columns got no section: {missing[:8]} -- the "
             f"walk fell out of step with the pairing and the grouping is "
             f"not trustworthy")

grouped = {}
for c in cols:
    grouped.setdefault(section_of[c["column"]], []).append(c["column"])

(SP / "universe_sections.json").write_text(json.dumps({
    "section_of": section_of,
    "grouped": grouped,
}, indent=1), encoding="utf-8")

print(f"{len(cols)} columns assigned to {len(grouped)} sections")
for name, members in grouped.items():
    gov = sum(1 for m in members if by_col[m]["governed"])
    print(f"  {len(members):4}  gov {gov:3}  {name[:66]}")
