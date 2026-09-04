"""
Multibagger score — screening contract test
===========================================
Proves the score survives every boundary between the database and the JSON the
client receives:

    universe column -> SELECT -> ScreenerRow -> serialised response

Run on the server, where pydantic is installed:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_multibagger_contract.py

The zero case is the one that matters most. Truthiness checks silently turn a
valid 0.0 into missing data, and a stock legitimately scoring zero on dilution
or on the composite must not be indistinguishable from one with no data at all.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIELDS = ("multibagger_potential_score", "mb_valid_weight_pct", "multibagger_version")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(label)


print("1. Field reaches the SELECT and survives the response model")
src = (Path(__file__).resolve().parents[1] / "app/api/v1/routes/screener.py").read_text(encoding="utf-8")
sql = re.search(r'data_sql = f"""(.*?)"""', src, re.S).group(1)
selected = set(re.findall(r"\bu\.([a-z_][a-z0-9_]*)", sql)) | \
           set(re.findall(r"\bAS\s+([a-z_][a-z0-9_]*)", sql, re.I))

sch = (Path(__file__).resolve().parents[1] / "app/schemas/screener.py").read_text(encoding="utf-8")
body = sch.split("class ScreenerRow", 1)[1].split("class ScreenerResponse", 1)[0]
declared = set(re.findall(r"^\s{4}([a-z_][a-z0-9_]*)\s*:", body, re.M)) - {"model_config"}

for f in FIELDS:
    check(f"{f} in SELECT", f in selected)
    check(f"{f} in ScreenerRow", f in declared)
stripped = sorted(selected - declared)
check("no SELECT column is stripped by the response model", not stripped, str(stripped))

print("\n2. Filterable and sortable")
allowed = re.search(r"ALLOWED_FIELDS: dict\[str, dict\] = \{(.*?)\n\}", src, re.S).group(1)
sortmap = re.search(r"SORTABLE_COLS[^=]*= \{(.*?)\n\}", src, re.S)
check("multibagger_potential_score in ALLOWED_FIELDS",
      '"multibagger_potential_score"' in allowed)
check("multibagger_potential_score in sort map",
      bool(sortmap) and '"multibagger_potential_score"' in sortmap.group(1))

print("\n3. Value preservation through the model")
from app.schemas.screener import ScreenerRow  # noqa: E402

base = dict(asx_code="TEST", company_name="Test Ltd")
for label, value in [("NULL stays NULL", None), ("0.0 stays 0.0", 0.0),
                     ("81.4 stays 81.4", 81.4), ("100.0 stays 100.0", 100.0)]:
    row = ScreenerRow(**base, multibagger_potential_score=value)
    dumped = row.model_dump()
    ok = dumped["multibagger_potential_score"] == value if value is not None \
        else dumped["multibagger_potential_score"] is None
    check(label, ok, f"got {dumped['multibagger_potential_score']!r}")

# A zero must be distinguishable from missing data, not merely equal to it.
zero = ScreenerRow(**base, multibagger_potential_score=0.0).model_dump()
null = ScreenerRow(**base, multibagger_potential_score=None).model_dump()
check("0.0 is not conflated with NULL",
      zero["multibagger_potential_score"] is not None
      and null["multibagger_potential_score"] is None)

print("\n4. Version string is carried, not coerced to a number")
row = ScreenerRow(**base, multibagger_version="MULTIBAGGER_POTENTIAL_V1")
check("version round-trips",
      row.model_dump()["multibagger_version"] == "MULTIBAGGER_POTENTIAL_V1")

print("\n5. NL prompt maps multibagger language to ranking, not filters")
ai = (Path(__file__).resolve().parents[1] / "app/api/v1/routes/ai.py").read_text(encoding="utf-8")
prompt = re.search(r'_NL_PROMPT = """(.*?)"""', ai, re.S).group(1).lower()
check("ranks on the composite", "rank multibagger_potential_score desc" in prompt)
check("forbids rebuilding from components", "do not reconstruct multibagger" in prompt)
check("forbids inventing a threshold", "do not invent a threshold" in prompt)
check("states it is not a return prediction", "does not predict returns" in prompt)
check("futuristic is not mapped to the score", "not a proxy for innovation" in prompt)

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED")
    sys.exit(1)
print("ALL CONTRACT CHECKS PASSED")
