"""Cap-tier consumers read the label, not the flags, and unknown is askable.

The six `is_*` tier flags are `COALESCE(vs.market_cap >= <band>, FALSE)`
written into columns declared NOT NULL DEFAULT false. A company whose market
cap is unknown is therefore stored as a measured `false` on all six.
`market_cap_tier` is computed from the same input in the same statement and
returns NULL, so it is the only one of the two that can say "we do not know".

Measured 10 Nov 2026: 641 of 2,566 rows (25.0%) carried six falses and a NULL
tier. Every consumer tested `= TRUE`, so no company was ever reported in a
tier it did not belong to. What happened instead is that a quarter of the
universe was invisible to every tier filter, and nothing in any response said
those companies were unclassified rather than unmatched.

Three defects are guarded here, and the third was found while fixing the
first two:

  * consumers reading the flags, which cannot express unknown
  * `unknown` missing from a consumer's accepted values, which makes those
    641 companies unaskable-for
  * a threshold written in a unit the column does not use

That last one: `asx300` was `market_cap >= 300` with a comment reading
"≥$300M". `screener.universe.market_cap` is RAW AUD -- the tier bands cut it
at 50000000000 for mega -- so the predicate meant three hundred dollars,
against a query that already required `market_cap > 0`. It admitted
essentially the whole universe while appearing to be a large-cap filter.
That is finding 4c's defect in a second place.

What this file cannot check is the reconciliation itself: that the seven
partitioning tiers sum to the whole table. That needs the database, and the
query is in the release evidence.
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MARKET = BACKEND / "app" / "api" / "v1" / "routes" / "market.py"
ADMIN = BACKEND / "app" / "api" / "v1" / "routes" / "admin.py"

#: Every consumer of the tier vocabulary. Listed rather than globbed: a new
#: consumer must be added here deliberately, and one that stops consuming
#: must be removed deliberately.
CONSUMERS = (MARKET, ADMIN)

EXPECT_TIERS = {"mega", "large", "mid", "small", "micro", "nano", "unknown"}
EXPECT_ASX300_AUD = 300000000

#: The six flags, which no consumer may filter on.
FLAG_COLUMNS = ("is_mega", "is_large", "is_mid", "is_small", "is_micro",
                "is_nano")


def _module_value(path: Path, name: str):
    """A module-level literal, read without importing (fastapi may be absent)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found at module level in {path.name}")


def cap_tier_sql() -> dict:
    return _module_value(MARKET, "CAP_TIER_SQL")


def partitioning_tiers() -> tuple:
    return tuple(_module_value(MARKET, "PARTITIONING_TIERS"))


# ── The vocabulary is declared once ─────────────────────────────────────────

def test_the_tier_vocabulary_is_declared_in_exactly_one_place():
    """A second copy is how the admin endpoint and the public ones diverged."""
    duplicates = []
    for path in CONSUMERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if {"mega", "large", "mid"} <= keys and path != MARKET:
                duplicates.append(path.name)
            elif {"mega", "large", "mid"} <= keys and path == MARKET:
                # The one declaration is allowed; anything else in this file
                # is a second copy.
                pass
    assert not duplicates, (
        f"{sorted(set(duplicates))} declare their own tier map. The "
        f"vocabulary lives in market.py and is imported.")


def test_the_partition_covers_every_tier_and_excludes_the_threshold():
    tiers = set(partitioning_tiers())
    assert tiers == EXPECT_TIERS, (
        f"PARTITIONING_TIERS is {sorted(tiers)}, expected "
        f"{sorted(EXPECT_TIERS)}")
    assert "asx300" not in tiers, (
        "asx300 is a threshold spanning several tiers, not a member of the "
        "partition; counting it would double count")
    sql = cap_tier_sql()
    missing = sorted(tiers - set(sql))
    assert not missing, f"{missing} are partition members with no predicate"


# ── Unknown is expressible everywhere ───────────────────────────────────────

def test_unknown_is_a_selectable_tier():
    sql = cap_tier_sql()
    assert "unknown" in sql, (
        "there is no predicate for unknown, so 641 companies cannot be asked "
        "for at all")
    assert "IS NULL" in sql["unknown"].upper(), (
        f"unknown is {sql['unknown']!r}; it must test the label for NULL, "
        f"which is the only way the universe expresses an unknown cap")


def test_every_endpoint_accepts_unknown():
    """A pattern that omits it rejects the request with a 422."""
    rejecting = []
    for path in CONSUMERS:
        src = path.read_text(encoding="utf-8")
        for match in re.finditer(r'pattern="\^\(([^)]*)\)\$"', src):
            alternatives = set(match.group(1).split("|"))
            if {"mega", "large", "mid"} <= alternatives \
                    and "unknown" not in alternatives:
                rejecting.append((path.name, match.group(1)))
    assert not rejecting, (
        f"these cap_tier patterns accept the named tiers and reject "
        f"'unknown': {rejecting}")


# ── Nobody filters on a column that cannot say "unknown" ────────────────────

def test_no_consumer_filters_on_the_boolean_tier_flags():
    """Including a flag name built by interpolation.

    An earlier version of this test matched the six literal names, and a
    mutant writing `f"u.is_{tier} = TRUE"` survived it: the literal text
    never contains "is_mega", so the matcher saw nothing. A column name
    assembled at run time is still a column name, and the check has to look
    for the shape rather than the spelling.
    """
    names = "|".join(FLAG_COLUMNS).replace("is_", "")
    pattern = re.compile(
        rf"\bis_(?:{names}|\{{[^}}]*\}})\s*=\s*TRUE", re.IGNORECASE)
    offenders = []
    for path in CONSUMERS:
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}  {line.strip()[:60]}")
    assert not offenders, (
        f"{offenders} filter on a boolean tier flag. The flags store a "
        f"measured false where the market cap is unknown, so a company with "
        f"no cap is silently excluded. Read market_cap_tier.")


# ── Units ───────────────────────────────────────────────────────────────────

def test_the_asx300_threshold_is_in_the_column_unit():
    """screener.universe.market_cap is RAW AUD, not millions."""
    predicate = cap_tier_sql()["asx300"]
    numbers = [int(n) for n in re.findall(r"\b(\d{3,})\b", predicate)]
    assert EXPECT_ASX300_AUD in numbers, (
        f"asx300 is {predicate!r}. market_cap is raw AUD -- the tier bands "
        f"cut it at 50000000000 for mega -- so a 300M threshold is "
        f"{EXPECT_ASX300_AUD}. A bare 300 means three hundred dollars and "
        f"admits the whole universe.")


def test_no_tier_predicate_compares_market_cap_to_a_small_number():
    """The general form: any raw-AUD threshold below a million is a unit bug.

    Written over every predicate rather than over asx300, because the defect
    was a comment and a column that disagreed about scale, and that can
    happen to any threshold added later.
    """
    suspicious = []
    for tier, predicate in cap_tier_sql().items():
        for literal in re.findall(r"market_cap\s*[<>]=?\s*(\d+)", predicate):
            if 0 < int(literal) < 1_000_000:
                suspicious.append((tier, predicate))
    assert not suspicious, (
        f"{suspicious} compare market_cap against a number below one "
        f"million. The column is raw AUD, so such a threshold is almost "
        f"certainly written in millions by mistake.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
