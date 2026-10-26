"""
A transform without its loader reads a table nothing fills
==========================================================
`pipeline_runner.py` holds two lists: STAGING_SCRIPTS (raw → staging) and
TRANSFORM_SCRIPTS (staging → market). On 26 Oct 2026 `transform_splits` sat
in the second list while `load_to_staging_splits` was absent from the first.

The transform therefore ran — successfully, exit 0 — against a staging table
that nothing had filled since April. `market.splits` last changed on
2026-04-28 and the gap went unnoticed for **181 days**, while the weekly
download kept writing fresh split payloads into the raw zone the whole time.

Nothing reported it, and the reason is worth keeping: the daily freshness
assertion derives its population from "the API reads this table AND a
scheduled job writes it". No scheduled job wrote market.splits, so the table
could not be stale by that definition. The check was correctly excluding the
one table that was wrong.

What it cost: every return on the site is computed from unadjusted close, so
a consolidation the table does not know about shows as a vast fake loss in
every return window spanning it. Three 1-for-10 and 1-for-20 consolidations
were found in September alone, none of them recorded.

So this asserts the pairing structurally, for every dataset rather than for
splits alone — the next one to be forgotten will not be this one.
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

V2 = BACKEND / "scripts" / "eodhd" / "v2"
RUNNER = V2 / "pipeline_runner.py"
WEEKLY = V2 / "jobs" / "weekly_pipeline.py"


def _list_names(var: str) -> list[str]:
    """The dataset names in a `NAME = [( "x", ... ), ...]` assignment."""
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"), str(RUNNER))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == var for t in node.targets):
            continue
        out = []
        for elt in getattr(node.value, "elts", []):
            parts = getattr(elt, "elts", [])
            if parts and isinstance(parts[0], ast.Constant):
                out.append(parts[0].value)
        return out
    raise AssertionError(f"{var} not found in {RUNNER}")


def test_the_runner_declares_both_stages():
    staging = _list_names("STAGING_SCRIPTS")
    transforms = _list_names("TRANSFORM_SCRIPTS")
    assert len(staging) >= 3, f"only {len(staging)} staging scripts parsed"
    assert len(transforms) >= 5, f"only {len(transforms)} transforms parsed"


def test_every_transform_with_a_loader_on_disk_has_it_registered():
    """The general rule, not the splits special case.

    If `load_to_staging_<name>.py` exists, somebody wrote a loader for that
    dataset — and a transform that runs without it rebuilds `market.<name>`
    from whatever happened to be in staging, which may be months old.
    """
    staging = set(_list_names("STAGING_SCRIPTS"))
    missing = []
    for name in _list_names("TRANSFORM_SCRIPTS"):
        loader = V2 / f"load_to_staging_{name}.py"
        if loader.exists() and name not in staging:
            missing.append(name)
    assert not missing, (
        "these datasets have a staging loader on disk and a transform "
        "registered, but no loader registered — their transforms run against "
        "a staging table nothing fills: " + ", ".join(sorted(missing)))


def test_splits_is_wired_end_to_end():
    """Named explicitly so removing it from the lists cannot quietly retire
    the case along with the coverage."""
    assert "splits" in _list_names("STAGING_SCRIPTS"), (
        "splits has no staging loader registered; market.splits will stop "
        "updating and every return spanning a consolidation goes wrong")
    assert "splits" in _list_names("TRANSFORM_SCRIPTS"), (
        "splits has no transform registered; staging would fill and "
        "market.splits would never see it")


def test_the_weekly_job_actually_runs_the_splits_chain():
    """Registration in pipeline_runner is not enough.

    pipeline_runner.py is in no cron entry. The weekly job runs the loaders
    and transforms it names directly, so a dataset missing THERE never runs
    in production however well it is registered here.
    """
    src = WEEKLY.read_text(encoding="utf-8")
    assert "load_to_staging_splits.py" in src, (
        "weekly_pipeline does not load splits — the registration in "
        "pipeline_runner.py does not run in production on its own")
    assert "transform_splits.py" in src, (
        "weekly_pipeline does not transform splits into market.splits")

    # Order matters: the transform truncates and rebuilds from staging when
    # run without --codes, so a transform ahead of its load would rebuild
    # market.splits from stale staging rows.
    assert src.index("load_to_staging_splits.py") < src.index("transform_splits.py"), (
        "transform_splits runs BEFORE its loader; it would truncate "
        "market.splits and rebuild it from whatever staging already held")


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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
