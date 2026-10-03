"""
One evaluator, two consumers, three states
===========================================
A job that takes the auxiliary lease and finds a canonical run in flight
returns without writing. Correct -- and indistinguishable from a quiet week,
because the process exits 0 either way and nothing reads the log line.

Three properties, and the third is the one that is easy to lose:

  * every deferrable job is covered, derived from the `auxiliary_lease` call
    sites rather than listed here, because a list of job names is exactly the
    thing that goes stale when someone adds the fifth job;
  * the scheduled gate and the admin surface are two consumers of ONE
    evaluator, so they cannot disagree about what "stale" means, and the
    surface never reads the gate's log -- a report of a report cannot tell
    "the job is fine" from "the checker stopped running";
  * `unobservable` is its own state. Not fresh, not failed. Two jobs whose
    output carries no timestamp must never read as two healthy ones.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_output_freshness.py
"""

import ast
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.output_freshness import (                      # noqa: E402
    ANCHORS, UNOBSERVABLE, Anchor, classify, existence_sql, latest_sql,
    summarise, unobservable_findings,
)

SCRIPT = BACKEND / "scripts/assert_output_freshness.py"
ADMIN = BACKEND / "app/api/v1/routes/admin.py"
MODULE = BACKEND / "compute/engine/output_freshness.py"

NOW = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)
# By name, never by position: this was ANCHORS[1] until two anchors were
# inserted ahead of it, at which point three tests began exercising a
# different anchor than they named.
PICKS = next(a for a in ANCHORS if a.job == "top5_strategy")


# ── Coverage: no deferrable job is silently absent ───────────────────────────

def _deferrable_jobs() -> set[str]:
    """Modules that CALL auxiliary_lease, not ones that merely mention it.

    Matching the bare string catches canonical_lease, which defines it, and
    launch_authority, which names it in a message -- neither is a job.
    """
    jobs = set()
    for path in (BACKEND / "compute/engine").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "auxiliary_lease"):
                jobs.add(path.stem)
                break
    return jobs


def test_every_deferrable_job_is_covered():
    covered = {a.job for a in ANCHORS} | set(UNOBSERVABLE)
    missing = _deferrable_jobs() - covered
    assert not missing, (
        f"these jobs defer silently and nothing proves they ever ran again: "
        f"{sorted(missing)}. Give each an anchor, or name it in UNOBSERVABLE "
        f"with the reason its output carries no timestamp.")


def test_the_detection_finds_the_real_jobs():
    """The mutation control. A detection that returned nothing would make the
    coverage test pass while covering nothing."""
    jobs = _deferrable_jobs()
    assert {"short_positions", "pros_cons", "asx_indices",
            "top5_strategy"} <= jobs
    assert "canonical_lease" not in jobs      # defines the helper
    assert "launch_authority" not in jobs     # names it in a message


def test_every_anchor_column_is_one_the_job_actually_writes():
    """An anchor is a guess until it is checked against the writer.

    The first version anchored top5_strategy on `created_at`; the job writes
    `computed_at`. A freshness check whose column does not exist proves
    exactly as much as no check at all.
    """
    for a in ANCHORS:
        # The writer is NAMED by the anchor rather than inferred from the job
        # name. Inferring it assumed every producer lived in compute/engine/,
        # which was true until prices were anchored — they are loaded from
        # scripts/eodhd/load_prices.py, and the inference would have rejected a
        # correct anchor.
        assert a.writer, f"{a.job} does not name the file that writes it"
        module = BACKEND / a.writer
        assert module.exists(), f"{a.job}: writer {a.writer} does not exist"
        assert a.column in module.read_text(encoding="utf-8"), (
            f"{a.job} is anchored on {a.column}, which does not appear in "
            f"{a.writer} -- the job does not write that column")


def test_unobservable_entries_carry_a_reason():
    """"Cannot be checked" is acceptable only with the reason attached.
    Without it the entry is a way to silence a job, not to describe one."""
    for job, why in UNOBSERVABLE.items():
        assert len(why) > 40, f"{job} is unobservable with no substantive reason"


def test_a_threshold_is_not_tighter_than_the_cadence():
    """A limit below the job's own period would fire on one deferral --
    exactly the behaviour the lease exists to produce -- and train people to
    ignore it."""
    # Measured against each job's OWN cadence. The original rule was a flat
    # 7-day floor, which was right while every anchor was weekly and became
    # wrong the moment a daily output was added: a 7-day floor on prices would
    # take longer to notice a stoppage than the September gap that prompted
    # the anchor. The property is "tolerates one deferral", not "is at least a
    # week".
    for a in ANCHORS:
        assert a.cadence_hours > 0, f"{a.job} declares no cadence"
        assert a.max_age_hours >= 2 * a.cadence_hours, (
            f"{a.job}: {a.max_age_hours}h is under two cadences "
            f"({a.cadence_hours}h), so one tolerated deferral would fire it")


# ── The classifier, behaviourally ────────────────────────────────────────────

def test_a_current_output_is_current():
    f = classify(PICKS, True, NOW - timedelta(hours=81), NOW)
    assert f.state == "current" and f.ok and not f.faulty
    assert f.age_hours == 81.0 and f.limit_hours == PICKS.max_age_hours


def test_stale_output_is_a_fault():
    """The mutation you cannot skip: past the limit must FAIL, not warn."""
    f = classify(PICKS, True, NOW - timedelta(hours=400), NOW)
    assert f.state == "stale" and f.faulty and not f.ok
    assert summarise([f])["healthy"] is False


def test_the_boundary_is_inclusive_not_approximate():
    """Exactly at the limit is current; one hour past it is not. A threshold
    nobody has tested at its own edge is a threshold nobody knows."""
    assert classify(PICKS, True,
                    NOW - timedelta(hours=PICKS.max_age_hours), NOW
                    ).state == "current"
    assert classify(PICKS, True,
                    NOW - timedelta(hours=PICKS.max_age_hours + 1), NOW
                    ).state == "stale"


def test_a_missing_column_is_broken_not_stale():
    """An instrument defect reported as a job defect sends someone to debug
    the wrong thing."""
    f = classify(PICKS, False, None, NOW)
    assert f.state == "broken" and f.faulty
    assert "does not exist" in f.reason


def test_an_empty_table_is_broken_not_stale():
    f = classify(PICKS, True, None, NOW)
    assert f.state == "broken" and "no rows at all" in f.reason


def test_a_naive_timestamp_is_read_as_utc():
    """psycopg2 can return naive datetimes depending on column type. Treating
    one as local time would shift the age by the server's offset and quietly
    change the verdict."""
    f = classify(PICKS, True, (NOW - timedelta(hours=10)).replace(tzinfo=None),
                 NOW)
    assert f.state == "current" and abs(f.age_hours - 10.0) < 0.01


# ── unobservable is NOT fresh ────────────────────────────────────────────────

def test_unobservable_is_neither_ok_nor_faulty():
    for f in unobservable_findings():
        assert not f.ok, f"{f.job} unobservable must not count as healthy"
        assert not f.faulty, f"{f.job} unobservable must not page anyone"


def test_unobservable_alone_is_not_healthy():
    """The control that keeps the honesty. If every observable anchor were
    deleted, the summary must NOT report healthy -- it would be proving
    nothing while looking green."""
    assert summarise(unobservable_findings())["healthy"] is False


def test_unobservable_is_counted_separately_and_visibly():
    s = summarise([classify(PICKS, True, NOW - timedelta(hours=1), NOW)]
                  + unobservable_findings())
    assert s["healthy"] is True
    assert s["current"] == 1
    assert s["unobservable"] == len(UNOBSERVABLE) == 2


# ── Two consumers, one evaluator ─────────────────────────────────────────────

def test_both_consumers_use_the_shared_evaluator():
    for consumer in (SCRIPT, ADMIN):
        src = consumer.read_text(encoding="utf-8")
        assert "output_freshness import" in src, (
            f"{consumer.name} does not import the shared evaluator")
        assert "classify(" in src, (
            f"{consumer.name} does not call the shared classifier -- it has "
            f"its own idea of what stale means")


def test_the_admin_surface_does_not_read_the_cron_log():
    """A surface that reports a report cannot distinguish "the job is fine"
    from "the checker stopped running"."""
    src = ADMIN.read_text(encoding="utf-8")
    assert "output_freshness.log" not in src
    assert "assert_output_freshness" not in src.replace(
        "scripts/assert_output_freshness.py", "")  # the docstring may name it


def test_the_evaluator_holds_no_connection():
    """It is pure so both drivers can use it. An import of psycopg2 or
    sqlalchemy here would bind it to one consumer."""
    src = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {n.names[0].name.split(".")[0]
                for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom)) and n.names}
    assert not ({"psycopg2", "sqlalchemy", "asyncpg"} & imported), imported


def test_the_shared_sql_is_paramstyle_neutral():
    """psycopg2 wants %s, SQLAlchemy text() wants :name. Carrying both would
    be two SQL strings pretending to be one."""
    sql = existence_sql(PICKS) + " " + latest_sql(PICKS)
    assert "%s" not in sql and "%(" not in sql
    assert not re.search(r":\w+", sql)


def test_the_sql_builder_refuses_a_hostile_identifier():
    """The identifiers are embedded because they come from a frozen registry.
    The guard exists so that stops being true loudly rather than silently."""
    hostile = Anchor("x", "public.t; DROP TABLE users--", "c", 24 * 7, "")
    try:
        existence_sql(hostile)
    except ValueError:
        return
    raise AssertionError("existence_sql embedded a non-identifier")


def test_the_gate_fails_by_default():
    """--report exists for a dashboard. The default must exit non-zero, or
    scheduling it proves nothing."""
    assert "return 0 if args.report else 1" in SCRIPT.read_text(encoding="utf-8")


# ── The September price gap: the fault this check was blind to ───────────────

def test_prices_are_anchored_at_all():
    """The defect, stated as a test.

    On 3 Oct 2026 a customer reported week-old prices. market.daily_prices had
    NO rows for 24, 25, 28 and 29 September, and this check reported FRESH
    throughout — truthfully, because its population was two secondary tables
    and the product's primary output was not in it.
    """
    anchored = {a.table for a in ANCHORS}
    assert "market.daily_prices" in anchored, (
        "prices are unwatched again; a customer will find the next gap")
    assert "screener.universe" in anchored, (
        "the served universe is unwatched; every metric could be stale")


def test_the_anchor_would_have_caught_the_real_gap():
    """Not a hypothetical. The newest trading day was 23 Sep; the check runs
    at 10:00 UTC daily. By Monday the 28th it must read stale."""
    from datetime import date
    prices = next(a for a in ANCHORS if a.job == "daily_prices")
    monday = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    assert classify(prices, True, date(2026, 9, 23), monday).state == "stale"


def test_a_normal_weekend_does_not_fire():
    """The control. An alarm that cries on every Sunday gets ignored by the
    second Sunday, and then the real gap goes unnoticed anyway."""
    from datetime import date
    prices = next(a for a in ANCHORS if a.job == "daily_prices")
    sunday = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    assert classify(prices, True, date(2026, 9, 25), sunday).state == "current"
    # A single public holiday on the Monday: checked that Monday, Friday's
    # close is one weekday behind and legitimate.
    monday = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    assert classify(prices, True, date(2026, 9, 25), monday).state == "current"


def test_two_weekdays_behind_is_a_fault_even_after_a_holiday():
    """Friday's close still newest on Tuesday means Monday AND Tuesday
    produced nothing. A Monday holiday does not excuse it: Tuesday's run
    should have loaded Tuesday."""
    from datetime import date
    prices = next(a for a in ANCHORS if a.job == "daily_prices")
    tuesday = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    assert classify(prices, True, date(2026, 9, 25), tuesday).state == "stale"


def test_a_date_column_is_handled_as_midnight_utc():
    """market.daily_prices.time is a DATE. `date` has no tzinfo, so the
    classifier would have raised on the very anchor that matters most."""
    from datetime import date
    prices = next(a for a in ANCHORS if a.job == "daily_prices")
    f = classify(prices, True, date(2026, 10, 2),
                 datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc))
    assert f.state == "current" and f.age_hours == 12.0


# ── Coverage: the unwatched set is reported, not hidden ──────────────────────

def test_coverage_reports_what_is_not_watched():
    """Two green anchors must never again read as "the data is fresh"."""
    from compute.engine.output_freshness import coverage
    relevant = {"market.daily_prices", "screener.universe",
                "market.dividends", "market.fx_rates"}
    c = coverage(relevant)
    assert c["relevant"] == 4
    assert "market.daily_prices" in c["anchored"]
    assert sorted(c["unclassified"]) == ["market.dividends", "market.fx_rates"]
    assert c["unclassified_count"] == 2


def test_coverage_does_not_claim_completeness_when_it_knows_nothing():
    """An empty population is not full coverage."""
    from compute.engine.output_freshness import coverage
    c = coverage(set())
    assert c["relevant"] == 0 and c["anchored"] == []
    assert c["anchored_outside_population"], (
        "anchors outside the derived population must be visible, not silently "
        "counted as covering it")


# ── The ratchet: the unwatched set may shrink, never grow ────────────────────

#: Measured 3 Oct 2026, the day prices were first anchored. This is a DEBT,
#: not a target. Lower it whenever a table is anchored or named; never raise
#: it to make a build pass.
MAX_UNWATCHED = 38


def test_the_unwatched_set_does_not_grow():
    """The gate that was missing when market.daily_prices went unwatched.

    Classifying all 41 freshness-relevant tables is real work, and demanding
    it in one go would either block this fix or invite someone to mark them
    all observable without checking. A ratchet gives the contract teeth today:
    a NEW table that the API serves and a job writes must be anchored or named
    at the time it is added, because it cannot push this count up.

    If this fails because the derived population grew, that is the test
    working. Anchor the new table, name it unobservable with a reason, or
    establish that it does not belong in the population — but do not raise the
    number to make it pass.
    """
    from compute.engine.canonical_boundary import freshness_relevant_tables
    from compute.engine.output_freshness import coverage
    c = coverage(freshness_relevant_tables())
    assert c["unclassified_count"] <= MAX_UNWATCHED, (
        f"{c['unclassified_count']} freshness-relevant tables are unwatched, "
        f"up from {MAX_UNWATCHED}. New: "
        f"{c['unclassified'][:5]}")


def test_the_ratchet_is_tightened_when_coverage_improves():
    """A ratchet left slack is not a ratchet. If the real count has fallen
    below the recorded debt, record the lower number."""
    from compute.engine.canonical_boundary import freshness_relevant_tables
    from compute.engine.output_freshness import coverage
    actual = coverage(freshness_relevant_tables())["unclassified_count"]
    assert actual >= MAX_UNWATCHED, (
        f"coverage improved to {actual} unwatched; lower MAX_UNWATCHED to "
        f"{actual} so the gain cannot be silently given back")


def test_the_population_is_derived_not_listed():
    """A hand-written population is how prices came to be unwatched."""
    import ast
    import inspect
    from compute.engine import canonical_boundary
    src = inspect.getsource(canonical_boundary.freshness_relevant_tables)
    assert "relations(" in src, "the population is no longer derived from source"

    # Docstring stripped first. It names market.daily_prices while explaining
    # why hand-listing is dangerous, and the first version of this assertion
    # read that explanation as the offence it warns about.
    fn = ast.parse(src.lstrip()).body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)):
        fn.body = fn.body[1:]
    code = ast.unparse(fn)
    assert "daily_prices" not in code, "the population names a table by hand"


# ── Registry members are selected by identity, never by position ─────────────

def test_no_positional_references_into_the_anchor_registry():
    """`PICKS = ANCHORS[1]` silently repointed three tests at a different
    anchor the moment two anchors were inserted ahead of it. Insertion order
    is not identity, and a registry is exactly the kind of thing that grows in
    the middle."""
    # Matched STRUCTURALLY, via the AST. A text search found this test's own
    # docstring, which quotes the pattern while explaining it — the third time
    # today a matcher in this repo has read prose as code. A subscript node is
    # not something a sentence can accidentally be.
    import ast
    for rel in ("tests/test_output_freshness.py",
                "compute/engine/output_freshness.py",
                "scripts/assert_output_freshness.py"):
        tree = ast.parse((BACKEND / rel).read_text(encoding="utf-8"))
        hits = [
            ast.unparse(n) for n in ast.walk(tree)
            if isinstance(n, ast.Subscript)
            and isinstance(n.value, ast.Name) and n.value.id == "ANCHORS"
            and isinstance(n.slice, ast.Constant)
            and isinstance(n.slice.value, int)
        ]
        assert not hits, (
            f"{rel} indexes ANCHORS positionally ({hits}); select by job name")


def test_the_freshness_semantic_is_described_conservatively():
    """Weekday/closure-aware lag is not an exchange trading calendar, and the
    consecutive-closure limitation is the proof. Promoting the heuristic in
    prose would make a future reader trust a session calendar that does not
    exist."""
    src = (BACKEND / "compute/engine/output_freshness.py").read_text(
        encoding="utf-8")
    assert "NOT an exchange trading calendar" in src, (
        "the limit of the heuristic is no longer stated")
    assert "CONSECUTIVE market" in src, (
        "the known consecutive-closure limitation was removed")


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
