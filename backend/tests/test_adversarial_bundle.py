"""
The bundle proves things about named runs
=========================================
Guards on the adversarial assertion bundle itself. Its job is to be believed
after a rehearsal, so the ways it could quietly lie matter more than usual:

    anchoring   an assertion about "the latest run" passes because some
                unrelated run exists, and the report then proves correct
                behaviour about the wrong lifecycle
    coverage    an assertion silently missing is indistinguishable from one
                that passed
    read-only   a bundle that writes to the database it is inspecting has
                changed the evidence it is reporting on

Structural properties are checked by parsing the module, not by scanning its
text. Five separate textual guards in this rollout matched comments or
docstrings instead of code; where the claim is about Python structure, the AST
is the instrument.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_adversarial_bundle.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

BUNDLE = BACKEND / "scripts" / "p0a_adversarial_assertions.py"
TREE = ast.parse(BUNDLE.read_text(encoding="utf-8"))


def _function(name: str) -> ast.FunctionDef:
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() is gone; this guard is now inert")


def _calls(fn: ast.FunctionDef, attr: str) -> list:
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == attr]


def _sql_literals(fn: ast.FunctionDef) -> list:
    """Every string constant in the function that looks like SQL."""
    return [n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and re.search(r"\bSELECT\b|\bUPDATE\b", n.value)]


# ── Anchoring ────────────────────────────────────────────────────────────────

def test_no_assertion_resolves_a_run_by_recency():
    """"The latest run" passes whenever any run exists.

    Every query against the lifecycle tables must bind a run id the operator
    named. The one ORDER BY in this file belongs to the shared resolver query,
    which is imported rather than written here.
    """
    offenders = []
    for case in ("case_b", "case_c", "case_d"):
        for sql in _sql_literals(_function(case)):
            flat = " ".join(sql.split())
            touches_lifecycle = re.search(
                r"compute_runs|compute_run_stages|compute_run_finalizations",
                flat)
            if not touches_lifecycle:
                continue
            if re.search(r"ORDER BY\s+.*(run_at|id)\s+DESC", flat, re.I):
                offenders.append(f"{case}: {flat[:70]}")
            # An explicit binding on the run's identity, under any alias:
            # `run_id = %s`, `r.id = %s`, `WHERE id = %s`. A JOIN condition
            # such as `f.run_id = r.id` binds nothing and does not count.
            if not re.search(r"\b\w*\.?(?:run_)?id\s*=\s*%s", flat):
                offenders.append(f"{case} (unbound run): {flat[:70]}")
    assert not offenders, (
        f"these resolve a run by recency rather than by name: {offenders}")


def test_each_case_requires_its_run_ids_before_connecting():
    """A missing id must refuse, not default. The refusal has to happen before
    the database is touched, or a half-run bundle reports partial results as
    though they were the whole."""
    main = _function("main")
    src = ast.get_source_segment(BUNDLE.read_text(encoding="utf-8"), main)
    assert "required = {" in src
    assert "return 2" in src, "a missing run id does not refuse"

    connect = src.index("psycopg2.connect")
    refuse = src.index("return 2")
    assert refuse < connect, (
        "the bundle connects before checking that its anchors were supplied")


def test_the_population_is_verified_against_the_runs_own_evidence():
    """Re-deriving the population without checking it lets it drift between
    the exercise and the assertions, and every 'every row in the rebuilt
    population' claim is then about a different set."""
    fn = _function("anchored_population")
    sql = " ".join(" ".join(s.split()) for s in _sql_literals(fn))
    assert "expected_set_hash" in sql, (
        "the population is not compared with the hash the run recorded")
    assert any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "set_hash"
               for n in ast.walk(fn)), "the captured population is never hashed"

    # Hashing it is not comparing it. The verdict passed to report.check must
    # be the comparison itself — a literal True there would leave the hash
    # computed, printed, and never actually checked against the run's record.
    compared = any(
        isinstance(n, ast.Compare)
        and {getattr(n.left, "id", None),
             *(getattr(c, "id", None) for c in n.comparators)}
        == {"ours", "recorded_hash"}
        for n in ast.walk(fn))
    assert compared, (
        "the captured population's hash is never compared with the "
        "expected_set_hash the run recorded, so the anchor is decorative")


# ── Coverage ─────────────────────────────────────────────────────────────────

def _assertion_names(case: str) -> list[str]:
    out = []
    for call in _calls(_function(case), "check"):
        if call.args and isinstance(call.args[0], ast.Constant):
            out.append(call.args[0].value)
    return out


def test_case_c_covers_every_required_assertion():
    names = " | ".join(_assertion_names("case_c"))
    required = {
        "1": "driver exited non-zero",
        "1b": "classified as InjectedFault",
        "2": "run_c plan_name",
        "3": "universe_build SUCCESS",
        "4": "run_c has no finalisation",
        "5": "zero rows carry run_c",
        "6": "rebuilt population compute_run_id IS NULL",
        "7": "no stale canonical metric_states",
        "10": "resolver excludes run_c",
        "10b": "rebuilt rows match no servable run",
    }
    missing = [f"{k} ({v})" for k, v in required.items() if v not in names]
    assert not missing, f"case C is missing assertions: {missing}"

    # Three more are made by helpers, so they do not appear as literals here.
    src = ast.get_source_segment(BUNDLE.read_text(encoding="utf-8"),
                                 _function("case_c"))
    for helper in ("_projection_withheld", "_marker_consistent", "_run_immutable"):
        assert helper in src, f"case C never calls {helper}"


def test_case_d_does_not_assert_arithmetic_adjacency():
    """The invariant is "a new run, never a resumed one" — not that the id
    allocator went unused in between. Anything else could consume the
    sequence, and the assertion would then fail for a reason that has nothing
    to do with the lifecycle."""
    src = ast.get_source_segment(BUNDLE.read_text(encoding="utf-8"),
                                 _function("case_d"))
    assert not re.search(r"run_c\s*\+\s*1|run_d\s*-\s*1", src), (
        "case D asserts id adjacency rather than ordering")
    assert "run_at" in src, "case D does not establish creation ordering"


def test_case_b_proves_the_reuse_rather_than_a_successful_pipeline():
    """Without these two, a full cycle that happened to pass would satisfy
    case B."""
    names = " | ".join(_assertion_names("case_b"))
    assert "yearly_compute did not run under run_b" in names
    assert "publication fingerprint equals the reused one" in names


def test_immutability_is_proved_by_attempting_a_write():
    """Checked by reading, it proves only that nobody happened to change it."""
    fn = _function("_run_immutable")
    sql = " ".join(_sql_literals(fn))
    assert "UPDATE screener.compute_runs" in sql, (
        "immutability is asserted by reading rather than by being refused")
    src = ast.get_source_segment(BUNDLE.read_text(encoding="utf-8"), fn)
    assert "SAVEPOINT" in src and "ROLLBACK TO SAVEPOINT" in src, (
        "the probe is not rolled back, so it either edits the run or leaves "
        "the transaction aborted")


# ── Read-only ────────────────────────────────────────────────────────────────

def test_the_bundle_never_commits():
    """It inspects evidence; writing would change what it is reporting on."""
    commits = [n for n in ast.walk(TREE)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "commit"]
    assert not commits, "the assertion bundle commits to the database"

    main_src = ast.get_source_segment(BUNDLE.read_text(encoding="utf-8"),
                                      _function("main"))
    assert "conn.rollback()" in main_src, (
        "the bundle does not roll back, so the immutability probe's aborted "
        "transaction is left open")
    assert "autocommit = False" in main_src


def test_the_bundle_uses_the_shared_definition_of_servable():
    """Its own copy could report that the resolver refuses a failed run while
    the resolver, reading a different query, serves it."""
    imports = {n.module for n in ast.walk(TREE) if isinstance(n, ast.ImportFrom)}
    assert "compute.engine.run_resolution" in imports
    names = {a.name for n in ast.walk(TREE) if isinstance(n, ast.ImportFrom)
             for a in n.names}
    assert "validated_run_ids" in names
    assert "plan_requirements AS (" not in BUNDLE.read_text(encoding="utf-8"), (
        "the bundle carries its own resolution query")


def test_the_projection_check_goes_through_the_real_projector():
    """A bespoke column check would prove the columns look revoked, not that
    the API refuses to serve them."""
    fn = _function("_projection_withheld")
    src = ast.get_source_segment(BUNDLE.read_text(encoding="utf-8"), fn)
    assert "project_row" in src and "OUTSIDE_SNAPSHOT" in src
    assert "row_projection" in src


def test_every_harness_subcommand_is_reachable():
    """A do_* function with no dispatch case is dead code.

    do_adversarial() existed for a full day with no `adversarial)` branch, so
    running it printed the usage text. I had "verified" the dispatch with
    `bash -n`, which only parses, and with a usage test that failed earlier on
    a missing PYBIN — a check that passed for the wrong reason, which is the
    failure mode this whole suite exists to catch.
    """
    sh = (BACKEND / "scripts" / "p0a_discovery.sh").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in sh.splitlines()
                     if not ln.strip().startswith("#"))

    defined = set(re.findall(r"^do_(\w+)\(\)", code, re.M))
    assert defined, "no do_* functions found; this guard is inert"

    # The terminator must be the one that closes THIS case block. The script
    # has earlier `case` statements (PLAN validation, the adversarial argument
    # check), so searching for the first "\nesac" lands before the dispatch and
    # slices an empty region — which then reports every function as
    # unreachable. A guard that is wrong in the loud direction is still wrong.
    start = code.index('case "${1')
    dispatch = code[start:code.index("\nesac", start)]
    # Its own case LABEL, not merely a mention. `all)` calls do_sentinel among
    # others, so searching for the function name finds it there and a
    # subcommand that lost its own label still looks reachable — invocable
    # only as part of `all`, never on its own.
    unreachable = sorted(
        name for name in defined
        if not re.search(rf"^\s*(?:[\w|]+\|)?{name}\)", dispatch, re.M))

    assert not unreachable, (
        f"these harness functions have no dispatch label and cannot be "
        f"invoked on their own: {unreachable}")


# ── The sentinel means the whole execution context ───────────────────────────

def test_the_sentinel_covers_every_authority():
    """d15 passed a PostgreSQL-only sentinel while flushing production Redis.
    "Sentinel unchanged" must not drift back to meaning "the database was
    unchanged"."""
    sh = (BACKEND / "scripts" / "p0a_discovery.sh").read_text(encoding="utf-8")
    body = sh[sh.index("capture_sentinel() {"):]
    body = body[:body.index("\n}")]
    for authority in ("capture_sentinel_postgres", "capture_sentinel_redis",
                      "capture_sentinel_email"):
        assert authority in body, f"the sentinel does not capture {authority}"


def test_the_redis_sentinel_is_a_census_not_a_declaration():
    sh = (BACKEND / "scripts" / "p0a_discovery.sh").read_text(encoding="utf-8")
    body = sh[sh.index("capture_sentinel_redis() {"):]
    body = body[:body.index("\n}")]
    assert "--scan" in body and "asx:screener:*" in body, (
        "the Redis sentinel does not census the keyspace a flush would empty")
    assert "md5sum" in body, (
        "only counts are captured, so a rewrite preserving the count is "
        "invisible")
    assert "UNAVAILABLE" in body, (
        "a missing redis-cli would silently record nothing and read as proof")


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
