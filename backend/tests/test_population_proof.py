"""
Set equality is the proof; counts are diagnostics
=================================================
The population-proof machinery, at the grains the four producers actually use.

Each producer owes a different identity. technical_compute owes a row per
(code, date); halfyearly_compute owes one per (code, fiscal_year);
period_metrics_compute owes one per (code, computed_date); transform_prices
owes a date-set digest per code. Collapsing them all to "company codes" would
make four different questions look like one, and the three that are really
about time would be answered by a proof that never examined time.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_population_proof.py
"""

import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.run_stages import (  # noqa: E402
    StageResult, render_key, report_population, set_hash,
)


class Log:
    """Collects what a producer would have printed."""

    def __init__(self):
        self.lines = []

    def _add(self, msg, *a):
        self.lines.append(msg % a if a else msg)

    info = error = warning = _add

    def text(self):
        return "\n".join(self.lines)


# ── Keys at any grain ────────────────────────────────────────────────────────

def test_composite_keys_render_unambiguously():
    """Two different keys must never collapse into one string."""
    a = render_key(("BHP", date(2026, 9, 15)))
    b = render_key(("BHP", date(2026, 9, 16)))
    assert a != b
    assert "2026-09-15" in a

    # The classic collision: a separator that can occur inside a part. If the
    # renderer joined on "-", ("AB", "C-D") and ("AB-C", "D") would be one key.
    assert render_key(("AB", "C-D")) != render_key(("AB-C", "D"))


def test_a_date_and_its_datetime_are_the_same_member():
    """Rendering through isoformat() keeps one calendar day one member."""
    from datetime import datetime
    assert render_key(date(2026, 9, 15)) == "2026-09-15"
    assert render_key(datetime(2026, 9, 15).date()) == render_key(date(2026, 9, 15))


def test_the_hash_does_not_depend_on_processing_order():
    keys = [("BHP", date(2026, 9, 15)), ("CBA", date(2026, 9, 15))]
    assert set_hash(keys) == set_hash(reversed(keys))


# ── What the proof must catch ────────────────────────────────────────────────

def test_equal_counts_over_different_members_fails():
    """The failure counts alone cannot see.

    A producer that wrote exactly as many rows as it owed, for a different set
    of companies, is broken. `written_count == expected_count` calls it clean.
    """
    expected = frozenset({("BHP", 2026), ("CBA", 2026)})
    written = frozenset({("BHP", 2026), ("NAB", 2026)})
    result = StageResult("halfyearly_compute", expected, written,
                         grain="asx_code+fiscal_year")

    assert len(expected) == len(written), "the premise of this test"
    assert not result.ok
    assert result.status == "failed"
    assert result.missing == {("CBA", 2026)}
    assert result.extra == {("NAB", 2026)}


def test_the_right_codes_at_the_wrong_date_fails():
    """Every company present, no row written today.

    This is the shape a code-only proof passes: the target still holds
    yesterday's row for everyone, and the consumer takes the latest row with
    no recency bound, so stale values are served as current ones.
    """
    yesterday, today = date(2026, 9, 15), date(2026, 9, 16)
    result = StageResult(
        "period_metrics_compute",
        frozenset({("BHP", today), ("CBA", today)}),
        frozenset({("BHP", yesterday), ("CBA", yesterday)}),
        grain="asx_code+computed_date")

    assert not result.ok
    assert {k[0] for k in result.missing} == {"BHP", "CBA"}

    # And the same data, proved at the grain that hides it:
    collapsed = StageResult(
        "period_metrics_compute",
        frozenset({"BHP", "CBA"}), frozenset({"BHP", "CBA"}))
    assert collapsed.ok, (
        "the point of this test: at code grain the identical run passes, "
        "which is why the date belongs in the key")


def test_extra_members_fail_as_loudly_as_missing_ones():
    """The producer wrote something its own domain does not account for, so
    one of the two is wrong and the run cannot say which."""
    result = StageResult("technical_compute",
                         frozenset({("BHP", date(2026, 9, 16))}),
                         frozenset({("BHP", date(2026, 9, 16)),
                                    ("XYZ", date(2026, 9, 16))}),
                         grain="asx_code+date")
    assert not result.ok
    assert result.extra == {("XYZ", date(2026, 9, 16))}


def test_a_digest_member_detects_a_hole_in_the_middle():
    """transform_prices' grain.

    Same code, same row count, same first and last date — one day swapped.
    A min/max/count comparison passes this; the date-set digest does not.
    """
    def digest(days):
        return set_hash([f"{d}" for d in days])

    src = ["2026-09-14", "2026-09-15", "2026-09-16"]
    tgt = ["2026-09-14", "2026-09-17", "2026-09-16"]
    assert len(src) == len(tgt) and min(src) == min(tgt)

    result = StageResult(
        "transform_prices",
        frozenset({("BHP", 3, digest(src))}),
        frozenset({("BHP", 3, digest(tgt))}),
        grain="asx_code+row_count+date_set_digest")
    assert not result.ok


# ── Reporting and its refusals ───────────────────────────────────────────────

def test_a_producer_cannot_pass_by_having_nothing_to_say():
    """An unscoped call with no result is an inert check, not a pass."""
    try:
        report_population(None, None, None, Log())
    except ValueError as e:
        assert "nothing to say" in str(e)
    else:
        raise AssertionError("a producer with no result was reported as passing")


def test_a_scoped_run_records_nothing_and_does_not_fail():
    log = Log()
    assert report_population(None, 7, None, log,
                             scoped_reason="a scoped run's expected population "
                                           "is not the source domain")
    assert "skipped" in log.text()


def test_the_proof_prints_the_grain_and_both_directions():
    log = Log()
    ok = report_population(
        None, None,
        StageResult("technical_compute",
                    frozenset({("BHP", date(2026, 9, 16)),
                               ("CBA", date(2026, 9, 16))}),
                    frozenset({("BHP", date(2026, 9, 16))}),
                    grain="asx_code+date"),
        log)
    out = log.text()
    assert not ok
    assert "asx_code+date" in out
    assert "POPULATION NOT COVERED" in out
    assert "missing sample" in out and "CBA" in out
    assert "expected, not written" in out and "written, not expected" in out


def test_the_grain_is_persisted_not_inferred():
    """A reader of compute_run_stages cannot tell 2,103 companies from 2,103
    company-days unless the record says which."""
    payload = StageResult("technical_compute", frozenset(), frozenset(),
                          {"errors": 0}, grain="asx_code+date").payload()
    assert payload["grain"] == "asx_code+date"
    assert payload["errors"] == 0


def test_samples_are_bounded_and_say_so_when_truncated():
    from compute.engine.run_stages import SAMPLE_LIMIT
    expected = frozenset((f"C{i:04d}", 2026) for i in range(SAMPLE_LIMIT * 3))
    payload = StageResult("halfyearly_compute", expected, frozenset(),
                          grain="asx_code+fiscal_year").payload()
    assert len(payload["missing_sample"]) == SAMPLE_LIMIT
    assert payload["missing_truncated"] is True


# ── FAILED evidence that outlives the rollback ───────────────────────────────

def _failed_result(**kw):
    return StageResult("transform_prices",
                       frozenset({("BHP", 3, "a")}), frozenset(),
                       {"full_run": True}, grain="asx_code+row_count", **kw)


def test_a_stage_can_fail_with_its_populations_in_agreement():
    """The shrink case.

    If staging legitimately halves, the rebuilt target matches it exactly — 0
    missing, 0 extra — and the replacement is still refused. Deriving failure
    from set equality alone would record that stage as a success.
    """
    agreed = frozenset({("BHP", 3, "a")})
    passing = StageResult("transform_prices", agreed, agreed)
    assert passing.ok and passing.status == "success"

    refused = StageResult("transform_prices", agreed, agreed,
                          failure_class="shrink_refused")
    assert not refused.ok and refused.status == "failed"
    assert "shrink_refused" in refused.summary(), (
        "a stage that failed with equal populations must not summarise as "
        "'0 missing; 0 extra', which reads as success")
    assert refused.payload()["failure_class"] == "shrink_refused"


def test_recording_a_failure_demands_a_classification():
    from compute.engine.run_stages import record_failed_stage_after_rollback
    try:
        record_failed_stage_after_rollback(
            "dsn", 7, _failed_result(), Log(),
            failure_class="", failure_message="something went wrong")
    except ValueError as e:
        assert "failure_class" in str(e)
    else:
        raise AssertionError("an unclassified failure was accepted")


def test_no_run_id_means_no_attribution_but_still_a_loud_log():
    from compute.engine.run_stages import record_failed_stage_after_rollback
    log = Log()
    assert not record_failed_stage_after_rollback(
        "dsn", None, _failed_result(), log,
        failure_class="population_not_covered", failure_message="mismatch")
    assert "cannot be attributed" in log.text()


def test_a_broken_evidence_write_never_masks_the_producer_failure():
    """The secondary connection is best-effort by design.

    It returns False and logs; the caller still exits non-zero, and publication
    stays blocked because there is no success row either way.
    """
    from compute.engine.run_stages import record_failed_stage_after_rollback
    log = Log()
    # An unreachable DSN: psycopg2.connect raises inside the helper.
    ok = record_failed_stage_after_rollback(
        "postgresql://nobody@127.0.0.1:1/nonexistent?connect_timeout=1",
        7, _failed_result(), log,
        failure_class="population_not_covered", failure_message="mismatch")
    assert ok is False
    assert "could not record FAILED stage evidence" in log.text()
    assert "publication remains blocked" in log.text()


class FakeCursor:
    """Answers the envelope's question, then the immutability check."""

    def __init__(self, existing_status=None):
        self.existing = existing_status
        self.statements = []
        self._answer = None

    def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split())[:60], params))
        if "current_database()" in sql:
            self._answer = ("asx_screener",)
        elif "SELECT status" in sql:
            self._answer = (self.existing,) if self.existing else None
        else:
            self._answer = None

    def fetchone(self):
        return self._answer

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def _with_fake_driver(cursor):
    """Swap psycopg2.connect for the duration of one call."""
    import psycopg2
    conn = FakeConn(cursor)
    real = psycopg2.connect
    psycopg2.connect = lambda dsn: conn
    return conn, (lambda: setattr(psycopg2, "connect", real))


def test_failed_evidence_is_written_on_its_own_connection_and_committed():
    from compute.engine.run_stages import record_failed_stage_after_rollback
    cur = FakeCursor()
    conn, restore = _with_fake_driver(cur)
    log = Log()
    try:
        ok = record_failed_stage_after_rollback(
            "dsn", 7, _failed_result(), log,
            failure_class="population_not_covered",
            failure_message="the rebuilt population does not match staging")
    finally:
        restore()

    assert ok is True
    assert conn.committed, "failure evidence was not committed"
    assert conn.closed, "the evidence connection was left open"

    sql = " ".join(s for s, _ in cur.statements)
    assert "current_database()" in sql, (
        "the evidence connection was built from a DSN and never proved which "
        "database it reached; a scratch run could write into production's "
        "evidence table")
    assert "INSERT INTO screener.compute_run_stages" in sql

    inserted = next(p for s, p in cur.statements if s.startswith("INSERT"))
    assert inserted[2] == "failed"


def test_an_existing_stage_row_is_never_overwritten():
    """A retry is a new run, not an edit to an identity already read."""
    from compute.engine.run_stages import record_failed_stage_after_rollback
    for existing in ("success", "failed"):
        cur = FakeCursor(existing_status=existing)
        _conn, restore = _with_fake_driver(cur)
        log = Log()
        try:
            ok = record_failed_stage_after_rollback(
                "dsn", 7, _failed_result(), log,
                failure_class="empty_rebuild", failure_message="no rows")
        finally:
            restore()
        assert ok is False
        assert not any(s.startswith("INSERT") for s, _ in cur.statements), (
            f"a '{existing}' row was overwritten")
        assert "retry is a new run" in log.text(), (
            f"the refusal did not explain itself: {log.text()!r}")


def test_the_failed_payload_says_the_data_was_rolled_back():
    """A reader of the row must not have to wonder whether the target was left
    half-written."""
    from dataclasses import replace
    failed = replace(_failed_result(), failure_class="empty_rebuild",
                     details={"full_run": True, "data_rolled_back": True,
                              "failure_message": "the rebuild produced no rows"})
    payload = failed.payload()
    assert payload["data_rolled_back"] is True
    assert payload["failure_class"] == "empty_rebuild"
    assert payload["failure_message"]
    assert not failed.ok


# ── Producer and consumer share one population definition ────────────────────

def test_the_excluded_instrument_types_are_defined_once():
    """Cycle A held technical_compute to covering SUNPG, a capital note that
    build_screener_universe deletes — a producer wider than its consumer.

    Two copies of the list would drift, and the drift shows up as a producer
    failing its proof over rows the product never serves.
    """
    from compute.engine.serving_population import (
        EXCLUDED_COMPANY_TYPES, excluded_types_predicate,
    )
    assert EXCLUDED_COMPANY_TYPES == ("notes", "preferred_stock")

    for rel in ("scripts/eodhd/v2/build_screener_universe.py",
                "compute/engine/technical_compute.py"):
        code = "\n".join(
            ln for ln in (BACKEND / rel).read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith(("#", "--")))
        assert "serving_population import" in code, (
            f"{rel} does not take the exclusion list from the shared module")
        assert '("notes", "preferred_stock")' not in code, (
            f"{rel} carries its own copy of the excluded types")

    # Importing the shared rule is not applying it. technical_compute's domain
    # SQL must actually carry the predicate, or the producer is held to
    # covering instruments the universe deletes — which is the defect.
    domain = (BACKEND / "compute/engine/technical_compute.py"
              ).read_text(encoding="utf-8")
    domain_sql = domain[domain.index("SOURCE_DOMAIN_SQL = f"):
                        domain.index('"""', domain.index("SELECT p.asx_code"))]
    assert "excluded_types_predicate(" in domain_sql, (
        "technical_compute imports the exclusion rule and does not apply it "
        "to its expected population")

    assert "'notes', 'preferred_stock'" in excluded_types_predicate("c")


def test_a_served_company_is_never_skipped_at_its_latest_date():
    """Skipping is how a three-month-old indicator poses as current.

    build_screener_universe takes ORDER BY date DESC LIMIT 1 with no recency
    bound. Cycle A found four codes — CINPA, EMUCA, MAUCA, MFGO — typed
    common_stock, all in the universe, whose prices never move, so RSI is a
    0/0 division and every indicator is NaN. Skipping them left June's numbers
    being served as today's.

    A row with NULL indicators says "this cannot be computed". No row at all
    says nothing, and the consumer fills that silence with the past.
    """
    import ast
    src = (BACKEND / "compute/engine/technical_compute.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    build_rows = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == "build_rows")
    assert any(a.arg == "keep_uncomputable" for a in build_rows.args.args), (
        "build_rows cannot keep a row whose indicators are all NaN")

    # The warm-up filter must be conditional, not unconditional.
    body = ast.get_source_segment(src, build_rows)
    assert 'if not keep_uncomputable:' in body, (
        "the warm-up filter still drops uncomputable rows unconditionally, so "
        "the latest date can go unwritten")

    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    main_src = ast.get_source_segment(src, main)
    assert "keep_uncomputable=True" in main_src, (
        "the latest-date-only path does not keep uncomputable rows")
    # And only there: a history rewrite would otherwise write millions of
    # empty warm-up rows.
    assert main_src.count("keep_uncomputable=True") == 1


def test_the_uncomputable_count_reaches_the_stage_evidence():
    """Otherwise rows with no indicators are indistinguishable from rows with
    good ones, and the proof passes while the screener shows blanks nobody
    accounted for."""
    src = (BACKEND / "compute/engine/technical_compute.py").read_text(encoding="utf-8")
    assert "rows_without_indicators" in src
    assert "INDEX_RSI_14 = INSERT_COLS.index" in src, (
        "the rsi_14 position is hardcoded; inserting a column above it would "
        "silently miscount")


# ── Full replacement is old-complete or new-complete, never partial ──────────

TRANSFORM_PRICES = BACKEND / "scripts/eodhd/v2/transforms/transform_prices.py"


def _code_lines():
    """Source with comments and blanks removed, so no guard can match its own
    explanation -- a mistake this codebase has made four times."""
    out = []
    for line in TRANSFORM_PRICES.read_text(encoding="utf-8").splitlines():
        body = line.split("#")[0].rstrip()
        if body.strip():
            out.append(body)
    return out


def test_the_truncate_is_not_committed_on_its_own():
    """The original defect.

    TRUNCATE; COMMIT; then rebuild 6.7M rows left market.daily_prices empty
    and DURABLY so for the length of the rebuild. Anything that went wrong in
    that window destroyed the price history with nothing to roll back to, and
    almost every producer downstream reads this table.
    """
    lines = _code_lines()
    trunc = next(i for i, l in enumerate(lines)
                 if "TRUNCATE TABLE market.daily_prices" in l)
    following = " ".join(lines[trunc + 1:trunc + 4])
    assert "conn.commit()" not in following, (
        "the TRUNCATE is committed before the reload replaces what it removed")


def test_no_commit_is_reachable_mid_replacement():
    """Every commit between the TRUNCATE and the guards must be unreachable on
    a full run, or the table can be left in a committed partial state."""
    lines = _code_lines()
    trunc = next(i for i, l in enumerate(lines)
                 if "TRUNCATE TABLE market.daily_prices" in l)
    # Up to the proof, not merely up to the shrink guard: a commit placed
    # between the guards and the proof would still publish a replacement the
    # proof had not yet approved.
    proof = next(i for i, l in enumerate(lines) if "ok = prove_population(" in l)

    for i in range(trunc, proof):
        if "conn.commit()" not in lines[i]:
            continue
        # Walk back to the condition governing this commit.
        indent = len(lines[i]) - len(lines[i].lstrip())
        context = " ".join(
            l for l in lines[max(0, i - 4):i]
            if len(l) - len(l.lstrip()) < indent and l.strip().startswith(("if", "elif")))
        assert "not is_full_run" in context, (
            f"line {i}: {lines[i].strip()!r} can commit part of a replacement")


def test_a_failing_code_aborts_the_full_run_rather_than_skipping_it():
    """Skip-and-continue is how a partial replacement gets committed: the
    rollback restores the TRUNCATE too, so the remaining codes would rebuild
    into a table that was never emptied."""
    lines = _code_lines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "except Exception as e:")
    block = " ".join(lines[start:start + 14])
    assert "is_full_run" in block and "return 1" in block, (
        "a per-code failure during a full run does not abort the run")


def test_every_refusal_routes_through_the_one_rollback_path():
    """Empty rebuild, sharp shrink and an uncovered population are three
    failure classes with one exit: a refusal that leaves the TRUNCATE
    committed is not a refusal.

    Asserted as "there is exactly one way out", rather than checking each
    message for a nearby rollback — a fourth refusal added later with its own
    bespoke exit would pass that check and still commit.
    """
    lines = _code_lines()
    classes = [l for l in lines if 'failure = ("' in l]
    assert len(classes) >= 3, f"expected three failure classes, found {classes}"

    returns = [l.strip() for l in lines
               if l.strip().startswith("return ") and "refuse(" in l]
    assert len(returns) == 1, (
        f"a full run has {len(returns)} refusal exits; each extra one is a "
        f"path that can skip the rollback")


def test_the_refusal_rolls_back_before_it_records_why():
    """Evidence must describe a replacement that definitively did not happen.

    Recording first would put the FAILED row inside the transaction that is
    about to discard it — which is the gap this whole mechanism closes.
    """
    lines = _code_lines()
    start = next(i for i, l in enumerate(lines) if l.startswith("def refuse("))
    body = lines[start:start + 30]

    rollback = next(i for i, l in enumerate(body) if "conn.rollback()" in l)
    record = next(i for i, l in enumerate(body)
                  if "record_failed_stage_after_rollback(" in l and "import" not in l)
    assert rollback < record, (
        "failure evidence is written before the rollback that makes it true")


def test_the_proof_gates_the_commit_rather_than_describing_it():
    """A proof that runs after the commit can only report the damage."""
    lines = _code_lines()
    proof = next(i for i, l in enumerate(lines) if "ok = prove_population(" in l)
    final = max(i for i, l in enumerate(lines) if "conn.commit()" in l)
    assert proof < final, "the population proof runs after the final commit"


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
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
