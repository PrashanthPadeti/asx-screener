"""screener.universe holds exactly one row per asx_code, and that is provable.

The claim is not "the primary key stops duplicates". It does, but by then a
fan-out has already happened: with 33 sources in one statement, a join that
contributes two rows for one company does not raise a duplicate-key error --
the second row wins the ON CONFLICT and the published figures come from
whichever row the planner emitted last. Nothing in the output says which.

So the property is checked at the source, one leg at a time:

  * the driving relation yields one row per asx_code
  * every plain join is ON a column that is the other side's unique key
  * every lateral either LIMIT 1s, or aggregates with no GROUP BY

Each leg also carries its population count. A regex that stops matching finds
zero sources and zero fan-out, which reads exactly like a clean statement --
the failure mode this project has already shipped once, where a freshness
check watching three of forty-one tables printed FRESH for four days.

Evidence is read from database/stm/evidence/universe_joins.json, regenerated
by backend/scripts/stm/universe_joins.py, so the guard and the mapping
document are checking the same extraction rather than two of them.
"""

import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
EVIDENCE = ROOT / "database" / "stm" / "evidence" / "universe_joins.json"
SNAP_DIR = ROOT / "database" / "stm"

#: Populations at the time of writing. Reconciliation, not configuration.
EXPECT_SOURCES = 33
EXPECT_LATERALS = 30
EXPECT_LIMIT_1 = 25
EXPECT_AGG_NO_GROUP = 5
EXPECT_PLAIN = 3

#: The driving relation. One row per asx_code comes from a UNIQUE PARTIAL
#: index on the base table, not from the view definition, so the index is
#: what this test looks for.
DRIVING = "market.companies_current"
DRIVING_BASE = "market.companies"


def sources() -> list[dict]:
    assert EVIDENCE.exists(), (
        f"{EVIDENCE} is missing. Run "
        f"`python backend/scripts/stm/universe_joins.py` from the repo root. "
        f"An absent evidence file must fail here rather than let the "
        f"cardinality tests pass over an empty list.")
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))["sources"]


def unique_keys() -> dict[str, list[list[str]]]:
    """table -> the column sets a UNIQUE constraint or index guarantees.

    Partial unique indexes are included WITH their predicate, because a
    unique key that only holds for some rows is only a key for those rows.
    """
    out: dict[str, list[list[str]]] = {}
    for path in sorted(SNAP_DIR.glob("snap_*.json")):
        snap = json.loads(path.read_text(encoding="utf-8"))
        for con in snap.get("constraints", []):
            schema, table, _, kind = con[0], con[1], con[2], con[3]
            if kind in ("p", "u"):
                out.setdefault(f"{schema}.{table}", []).append(list(con[5]))
        for idx in snap.get("indexes", []):
            schema, table, _, is_unique = idx[0], idx[1], idx[2], idx[3]
            if not is_unique:
                continue
            inner = re.search(r"USING btree \(([^)]*)\)", idx[5] or "")
            if inner:
                cols = [c.strip().split()[0].strip('"')
                        for c in inner.group(1).split(",")]
                out.setdefault(f"{schema}.{table}", []).append(cols)
    return out


# ── Populations first ───────────────────────────────────────────────────────

def test_the_source_population_did_not_collapse():
    srcs = sources()
    assert len(srcs) == EXPECT_SOURCES, (
        f"{len(srcs)} sources parsed from the statement, expected "
        f"{EXPECT_SOURCES}. A parse that finds fewer sources finds fewer "
        f"fan-out risks, and reports a clean statement either way.")


def test_the_lateral_and_plain_populations_did_not_collapse():
    srcs = sources()
    lat = [s for s in srcs if s["kind"] == "lateral"]
    plain = [s for s in srcs if s["kind"] != "lateral"]
    assert len(lat) == EXPECT_LATERALS, \
        f"{len(lat)} laterals, expected {EXPECT_LATERALS}"
    assert len(plain) == EXPECT_PLAIN, \
        f"{len(plain)} plain sources, expected {EXPECT_PLAIN}"
    assert sum(1 for s in lat if s["limit_1"]) == EXPECT_LIMIT_1, \
        f"laterals with LIMIT 1 is not {EXPECT_LIMIT_1}"
    assert sum(1 for s in lat
               if s.get("aggregate_no_group")) == EXPECT_AGG_NO_GROUP, \
        f"aggregating laterals is not {EXPECT_AGG_NO_GROUP}"


def test_every_source_has_a_resolvable_base_table():
    """A source whose base table did not parse cannot be checked at all."""
    blind = [s["alias"] for s in sources() if not s["base_tables"]]
    assert not blind, (
        f"{blind} are sources whose base table could not be read. Their "
        f"cardinality is unknown, which is not the same as safe.")


# ── The property, one leg at a time ─────────────────────────────────────────

def test_the_driving_relation_is_one_row_per_code():
    srcs = sources()
    driver = [s for s in srcs if s["kind"] == "FROM"]
    assert len(driver) == 1, f"{len(driver)} driving relations, expected 1"
    assert driver[0]["base_tables"] == [DRIVING], (
        f"the statement now drives from {driver[0]['base_tables']}, not "
        f"{DRIVING}; the uniqueness argument below is about {DRIVING}")

    guard = None
    for path in sorted(SNAP_DIR.glob("snap_*.json")):
        snap = json.loads(path.read_text(encoding="utf-8"))
        for idx in snap.get("indexes", []):
            if (f"{idx[0]}.{idx[1]}" == DRIVING_BASE and idx[3]
                    and "asx_code" in (idx[5] or "")
                    and "is_current" in (idx[5] or "")):
                guard = idx[5]
    assert guard, (
        f"no UNIQUE index on {DRIVING_BASE}(asx_code) WHERE is_current was "
        f"found in any snapshot. Without it {DRIVING} can return two current "
        f"rows for one company and every figure in that company's universe "
        f"row comes from whichever the planner emitted last.")


def test_every_plain_join_is_on_a_unique_key_of_its_own_table():
    keys = unique_keys()
    bad = []
    for s in sources():
        if s["kind"] == "lateral" or s["kind"] == "FROM":
            continue
        table = s["base_tables"][0]
        on = (s.get("on") or [""])[0]
        cols = set(re.findall(r"\b(?:[a-z]+)\.([a-z_][a-z0-9_]*)", on))
        satisfied = any(set(k) <= cols for k in keys.get(table, []))
        if not satisfied:
            bad.append({"alias": s["alias"], "table": table, "on": on,
                        "unique_keys": keys.get(table, [])})
    assert not bad, (
        f"these joins are not on a unique key of the joined table and can "
        f"contribute more than one row per company: {bad}")


def test_no_lateral_can_return_more_than_one_row():
    loose = [{"alias": s["alias"], "base": s["base_tables"]}
             for s in sources()
             if s["kind"] == "lateral" and not s["at_most_one_row"]]
    assert not loose, (
        f"these laterals neither LIMIT 1 nor aggregate without GROUP BY, so "
        f"they fan the driving row out: {loose}")


def test_every_limit_1_lateral_picks_a_determined_row():
    """LIMIT 1 yields one row. Which row is a separate question.

    Cardinality and determinism are not the same property, and only the
    first is settled by LIMIT 1. A lateral that returns one arbitrary row
    does not fan out and can still serve the wrong period -- "the latest
    half" becoming whichever half the heap happened to return.

    Two forms are determined, and the statement uses both:

      ORDER BY ... LIMIT 1    the order names the row
      WHERE <unique key>      the predicate names it, and LIMIT 1 is only a
                              guard against a duplicate that should not exist

    The second form is why an earlier version of this test was WRONG. It
    flagged twelve laterals for having no ORDER BY; all twelve pin an
    equality on a unique key -- `fiscal_year = pnl0.fiscal_year - 1` for the
    annual ones, `UNIQUE (asx_code)` for the three staging_au tables, the
    unique partial index for `mc`. Six of them carry a comment saying so.
    The code was right and the guard was asserting a property the code had
    never claimed, which is how a guard built on an explanation passes a
    live defect while failing correct code.
    """
    keys = unique_keys()
    undetermined = []
    for s in sources():
        if s["kind"] != "lateral" or not s["limit_1"] or s["order_by"]:
            continue
        eq = set(s.get("eq_columns") or [])
        table = s["base_tables"][0] if s["base_tables"] else None
        covered = any(set(k) <= eq for k in keys.get(table, []))
        if not covered:
            undetermined.append({"alias": s["alias"], "table": table,
                                 "eq_columns": sorted(eq),
                                 "unique_keys": keys.get(table, [])})
    assert not undetermined, (
        f"these laterals take LIMIT 1 with no ORDER BY and no equality on a "
        f"unique key, so they return one ARBITRARY row: {undetermined}. Give "
        f"each an ORDER BY that names the row it means -- the planner will "
        f"not choose for you twice the same way.")


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
