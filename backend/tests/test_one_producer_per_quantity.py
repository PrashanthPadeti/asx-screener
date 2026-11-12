"""A quantity has one producer, and what is derived from it reads that one.

Finding 13, generalised. The universe statement carried a lateral, `dp52`,
that computed the 52-week extremes a SECOND time:

    SELECT MAX(high) AS high_52w, MIN(low) AS low_52w
      FROM market.daily_prices
     WHERE asx_code = c.asx_code
       AND time >= NOW() - INTERVAL '365 days'

`market.daily_metrics.high_52w` already existed and was governed. The two
disagreed in three ways, and each one published a wrong number rather than
an absent one:

  no coverage rule   rolling_extreme() blanks a row whose series does not
                     span 365 days and records why. MAX(high) over the
                     window returns the maximum of whatever is there, so a
                     stock with 196 days of history got a "52-week high"
                     drawn from six months.
  raw, not adjusted  technical_compute reads high_adj where it exists,
                     deliberately -- raw prices put the exchange's worst
                     performers at the top of "best 1-year return" after
                     their consolidations. dp52 read raw `high`. A 1-for-10
                     leaves the raw high ten times the adjusted one, so a
                     stock AT its 52-week high published at 10% of it.
  nothing recorded   no state, no reason, no attribution.

The canonical commit overwrites `screener.universe.high_52w` with the
governed assessment, so the extreme and the ratios published beside it came
from different computations. That is the whole defect, and it is not
specific to 52-week highs.

WHAT THIS FILE ASSERTS, AND WHY IT IS NOT A SPELLING CHECK
----------------------------------------------------------
Pinning "price_to_52w_high must read dm" would pass forever and teach
nothing. The property is general:

    a lateral in this statement may not produce a quantity that a table the
    statement already joins also publishes

and

    a published ratio must read its denominator from the same alias that
    publishes that denominator

Both are checked over the whole statement, not over the four columns that
went wrong. The first found exactly one offender when it was written --
dp52 -- which is the point: it was written to find the class, and the class
had one member.

LEGITIMATE MULTI-ALIAS READS
----------------------------
Reading one column name through two aliases is not by itself a defect, and
the test must not say it is:

    bs0 / bs1   the same balance-sheet column at two PERIODS. Year-over-year
                comparison is the intent, and both aliases resolve to the
                same table.
    cm / ym     a declared COALESCE fallback chain between
                market.computed_metrics and market.yearly_metrics. That
                pattern has its own guard and its own diagnostic
                (measure_evidence_identity_exposure.py); it is a fallback,
                not a second computation.

What makes dp52 different is that it COMPUTED the quantity rather than
reading a stored one. That is the discriminator these tests use.
"""

import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
EVIDENCE = ROOT / "database" / "stm" / "evidence" / "universe_joins.json"
PAIRS = ROOT / "database" / "stm" / "evidence" / "universe_pairs.json"
SNAP_DIR = ROOT / "database" / "stm"

#: Gold producers whose columns a lateral must not recompute. Listed rather
#: than globbed over every snapshot: a lateral aggregating a Silver price
#: table is how several legitimate columns are built (avg_volume_20d), and
#: the rule is about GOLD quantities, which have producers and governance.
PRODUCER_TABLES = ("market.daily_metrics",)

#: Laterals allowed to produce a name a producer table also carries.
#:
#: Empty, and it should stay that way. An entry here is a statement that two
#: definitions of one quantity are intended, which needs the reason written
#: beside it and a measurement showing they agree.
SHADOW_EXEMPT: dict[str, str] = {}


def sources() -> list[dict]:
    assert EVIDENCE.exists(), (
        f"{EVIDENCE} is missing. Run "
        f"`python backend/scripts/stm/universe_joins.py` from the repo root.")
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))["sources"]
    assert data, "the join evidence is empty; every assertion below would pass"
    return data


def columns() -> list[dict]:
    assert PAIRS.exists(), (
        f"{PAIRS} is missing. Run "
        f"`python backend/scripts/stm/universe_pairs.py` from the repo root.")
    data = json.loads(PAIRS.read_text(encoding="utf-8"))["columns"]
    assert data, "the column evidence is empty; every assertion below passes"
    return data


def producer_columns() -> dict[str, set[str]]:
    """table -> its column names, from the schema snapshots."""
    out: dict[str, set[str]] = {}
    for path in sorted(SNAP_DIR.glob("snap_*.json")):
        snap = json.loads(path.read_text(encoding="utf-8"))
        for table, rows in (snap.get("columns") or {}).items():
            if table in PRODUCER_TABLES:
                out.setdefault(table, set()).update(r[0] for r in rows)
    return out


# ── Population first ────────────────────────────────────────────────────────

def test_the_producer_tables_were_actually_found():
    """Otherwise the shadow test compares against an empty set and passes.

    This is the failure mode the check exists to avoid in itself: a guard
    whose population quietly became zero while it kept reporting success.
    """
    found = producer_columns()
    missing = [t for t in PRODUCER_TABLES if not found.get(t)]
    assert not missing, (
        f"no columns found for {missing} in any database/stm/snap_*.json. "
        f"The shadow check would compare every lateral against an empty set "
        f"and report no offenders for the same reason a broken check does.")
    for table, cols in found.items():
        assert len(cols) > 20, (
            f"{table} snapshot lists only {len(cols)} columns, which is too "
            f"few to be the real table")


def test_some_lateral_declares_outputs():
    """The evidence must carry what laterals produce, not only what they read.

    Until 13 Nov 2026 it did not, and that is precisely why no guard could
    ask the shadow question. An evidence file that stopped recording outputs
    would make the test below vacuous.
    """
    declared = [s for s in sources() if s.get("outputs")]
    assert declared, (
        "no lateral in the evidence declares any output column. Either the "
        "statement has none, which is false, or universe_joins.py stopped "
        "recording them and the shadow check below is testing nothing.")


# ── The property ────────────────────────────────────────────────────────────

def test_no_lateral_recomputes_a_governed_producers_quantity():
    offenders = []
    producers = producer_columns()
    for src in sources():
        alias = src.get("alias")
        if alias in SHADOW_EXEMPT:
            continue
        outputs = set(src.get("outputs") or ())
        if not outputs:
            continue
        for table, cols in producers.items():
            clash = sorted(outputs & cols)
            if clash:
                offenders.append(
                    f"{alias} (reads {', '.join(src.get('base_tables') or [])}) "
                    f"produces {clash}, which {table} already publishes")
    assert not offenders, (
        "these laterals compute a quantity a joined producer already "
        "publishes, which is how two definitions of one number end up in "
        "adjacent columns of the same row:\n  "
        + "\n  ".join(offenders)
        + "\nRead the producer's column instead, or add an entry to "
          "SHADOW_EXEMPT with the reason and a measurement showing the two "
          "agree.")


def test_a_ratio_reads_its_denominator_from_the_publishing_alias():
    """price_to_X must divide by the same X the row publishes.

    The specific failure: `price_to_52w_high` divided by `dp52.high_52w`
    while the row's `high_52w` column came from somewhere else entirely. A
    reader comparing the two columns was comparing two different
    measurements, and nothing on the row said so.
    """
    cols = columns()
    expr_by_column = {c["column"]: c["expr"] for c in cols}
    ref = re.compile(r"\b([a-z][a-z0-9_]{0,12})\.([a-z_][a-z0-9_]*)\b")

    def aliases_for(column: str, wanted: str) -> set[str]:
        return {a for a, col in ref.findall(expr_by_column.get(column, ""))
                if col == wanted}

    # Derived column -> the column it is a ratio of. By meaning, not by a
    # naming rule: price_to_52w_high pairs with high_52w because of what it
    # measures, and a rule that guessed the pairing would guess the next
    # one wrong with equal confidence.
    pairs = {
        "price_to_52w_high": "high_52w",
        "price_to_52w_low":  "low_52w",
        "new_52w_high":      "high_52w",
        "new_52w_low":       "low_52w",
    }

    missing = [d for d in pairs if d not in expr_by_column]
    assert not missing, (
        f"{missing} are not columns of this statement. Either they were "
        f"removed, or the pairing above has gone stale and this test is "
        f"checking nothing.")

    mismatched = []
    for derived, base in pairs.items():
        base_alias = aliases_for(base, base)
        derived_alias = aliases_for(derived, base)
        if not derived_alias:
            mismatched.append(
                f"{derived} does not read {base} from any alias at all")
        elif base_alias and derived_alias != base_alias:
            mismatched.append(
                f"{derived} reads {base} from {sorted(derived_alias)} while "
                f"the row publishes {base} from {sorted(base_alias)}")
    assert not mismatched, (
        "a derived column and the quantity it derives from come from "
        "different sources:\n  " + "\n  ".join(mismatched))


def test_no_boolean_asserts_a_negative_from_an_unknown_input():
    """`... IS NOT NULL ... THEN TRUE ELSE FALSE` publishes a measured false.

    The two new-high flags were written exactly that way, so a stock whose
    52-week high was unknown was published as having definitely not made a
    new one. The columns are nullable with no default: the schema could
    always hold the third answer.

    A plain `ELSE 0` inside a counting expression is not this -- it
    contributes to a sum rather than asserting a fact -- so the check looks
    for a CASE that both guards an input for NULL and falls back to a
    boolean literal.
    """
    guarded = re.compile(r"IS\s+NOT\s+NULL", re.I)
    else_bool = re.compile(r"\bELSE\s+(?:TRUE|FALSE)\b", re.I)
    offenders = [
        c["column"] for c in columns()
        if guarded.search(c["expr"]) and else_bool.search(c["expr"])
    ]
    assert not offenders, (
        f"{offenders} test an input for NULL and then fall back to a "
        f"boolean literal. Where the input is absent this publishes a "
        f"confident negative that nobody measured. Return the comparison "
        f"from the CASE instead, so the three outcomes stay distinct: "
        f"TRUE, FALSE, and NULL for 'we do not know'.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:                               # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
