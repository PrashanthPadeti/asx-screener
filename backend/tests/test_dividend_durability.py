"""
The dividend chain is scheduled, complete, and asserts what it produced
=======================================================================
Between May and September 2026 market.dividends aged four months while the
weekly download kept arriving on time. Nothing was broken. The raw zone was
current, every scheduled job exited zero, and no alert fired — because the two
steps that turn downloaded files into the table the engine reads were **not in
the pipeline at all**. A pipeline cannot report a step it does not have.

Repaired by hand: 19,063 -> 29,804 rows, 750 -> 1,235 issuers, 485 issuers
with no dividend history whatsoever. That repair is not durable until it is
scheduled, and a schedule is not durable until something fails when it drifts.

These tests are that something. They are textual because the failure mode is
absence — a missing step cannot be caught by testing the steps that exist, and
the only artefact that records the intended sequence is the pipeline source.

Three properties, each corresponding to a way the original defect could
return:

    presence   all three steps are in the weekly pipeline
    order      load precedes transform precedes assertion, and the whole
               chain precedes anything that reads market.dividends
    teeth      the assertion runs without --warn-only, so an unhealthy feed
               fails the job rather than being noted in a log nobody reads

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_dividend_durability.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND = Path(__file__).resolve().parents[1]
PIPELINE = BACKEND / "scripts" / "eodhd" / "v2" / "jobs" / "weekly_pipeline.py"
ASSERTER = BACKEND / "scripts" / "assert_feed_health.py"

LOAD = "load_to_staging_dividends.py"
TRANSFORM = "transform_dividends.py"
ASSERT = "assert_feed_health.py"


def _code(path: Path) -> str:
    """Source without comment lines. The comments describe the outage by name,
    and a guard that matches its own explanation proves nothing."""
    return "\n".join(
        ln for ln in path.read_text(encoding="utf-8").splitlines()
        if not ln.strip().startswith("#"))


def test_all_three_steps_are_in_the_weekly_pipeline():
    """Presence. The original defect was absence, not error."""
    code = _code(PIPELINE)
    missing = [s for s in (LOAD, TRANSFORM, ASSERT) if s not in code]

    assert not missing, (
        f"the weekly pipeline does not run: {missing}. This is the shape of "
        f"the May-September 2026 outage — downloads arriving, nothing loading "
        f"or transforming them, and no job failing to say so.")


def test_the_chain_runs_in_order():
    """Order. A transform ahead of its load transforms last week's staging,
    and an assertion ahead of its transform certifies the feed it replaced."""
    code = _code(PIPELINE)
    load, transform, assert_ = (code.index(LOAD), code.index(TRANSFORM),
                                code.index(ASSERT))

    assert load < transform, "transform runs before the staging load"
    assert transform < assert_, "feed health is asserted before the transform"


def test_the_chain_precedes_every_consumer_of_market_dividends():
    """The universe build reads market.dividends for ex_div_date, and the
    compute engines read it for every dividend metric. Transforming after them
    would publish a week-old feed under this run's name."""
    code = _code(PIPELINE)
    assert_at = code.index(ASSERT)

    for consumer in ("build_screener_universe.py", "composite_score.py",
                     "yearly_compute.py"):
        assert consumer not in code or code.index(consumer) > assert_at, (
            f"{consumer} runs before the dividend feed is transformed and "
            f"asserted; it would consume the previous week's dividends")


def test_the_assertion_has_teeth():
    """--warn-only exists for inspection. A scheduled job using it would turn
    the one step that can fail the pipeline into a log line."""
    code = _code(PIPELINE)
    window = code[max(0, code.index(ASSERT) - 400):code.index(ASSERT) + 400]

    assert "--warn-only" not in window, (
        "the scheduled feed-health assertion is running with --warn-only; an "
        "unhealthy feed would no longer fail the weekly job")


def test_the_assertion_uses_the_engine_classifier_and_declares_no_thresholds():
    """One classifier.

    An operational definition of "healthy" beside the financial one drifts
    from it silently: the scheduler reports success while the factor engine
    withholds every dividend metric, and neither is wrong by its own lights.
    So this script must import the thresholds, never restate them.
    """
    code = _code(ASSERTER)

    assert "fetch_feed_health" in code, "the assertion does not call the classifier"
    assert re.search(r"from compute\.engine\.dividends import", code), (
        "the assertion must import from the module that owns the contract")

    # A literal 35, 20 or 30 next to a threshold name means the numbers have
    # been copied rather than imported.
    for name in ("FEED_STALENESS_DAYS", "MIN_RECENT_ROWS", "MIN_RECENT_ISSUERS"):
        assert not re.search(rf"{name}\s*=\s*\d+", code), (
            f"{name} is assigned a literal here; it must come from "
            f"compute.engine.dividends")


def test_the_classifier_is_importable_without_the_compute_engine():
    """The weekly chain needs the classifier and none of the factor engine.

    fetch_feed_health used to live in daily_compute, which meant importing it
    dragged pandas, the domain resolver and the whole applicability contract
    along — and made it unavailable on a branch where that engine differs.
    """
    from compute.engine import dividends

    assert hasattr(dividends, "fetch_feed_health")

    # MODULE-level imports only. DividendSource.assessments() imports the
    # applicability contract inside the function, and that is fine: it is the
    # factor engine's path, not the scheduler's, and it costs nothing to a
    # caller that only wants fetch_feed_health. The distinction matters --
    # the first version of this test matched the function-local import and
    # failed correct code, which is how guards get switched off.
    src = Path(dividends.__file__).read_text(encoding="utf-8")
    module_level = [ln for ln in src.splitlines()
                    if re.match(r"^(from|import)\s", ln)]

    for line in module_level:
        assert "compute.engine" not in line and "pandas" not in line, (
            f"dividends.py gained a module-level heavy import: {line!r}. The "
            f"feed classifier must stay usable by a scheduler that wants no "
            f"compute engine.")


def test_the_bounded_window_survives():
    """An announcement is not an observation.

    The classifier once used an unbounded MAX(ex_date). After the September
    reload the table held rows out to 2026-12-16, so the lag came out at -94
    days and -94 <= 35 reported a dead feed as healthy — the inverse of the
    original defect and strictly worse.
    """
    from compute.engine.dividends import fetch_feed_health
    from datetime import date

    seen = {}

    class Cur:
        def execute(self, sql, params=None):
            seen["sql"], seen["params"] = sql, params
        def fetchone(self):
            return (date(2026, 9, 15), 353, 352, 100)

    h = fetch_feed_health(Cur(), as_of=date(2026, 9, 16))

    assert "ex_date <= CURRENT_DATE" in seen["sql"], (
        "the freshness window is no longer bounded above by today; future "
        "announcements would count as freshness")
    assert seen["params"] and "window" in seen["params"], (
        "the staleness threshold is no longer a bound parameter")
    assert h.lag_days == 1 and h.healthy is True
    assert h.future_announced == 100, "future rows must be counted separately"


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
