"""
Desired state and observed state must agree
===========================================
`setup_cron.sh` is what code review can reason about; `crontab -l` is what can
actually mutate production. Neither is truth alone, and neither is rewritten
to match the other — they must AGREE on every canonical-relevant entry, and
where they do not, that is a finding.

The reconciliation half only runs where a crontab exists, so it SKIPS off the
server rather than passing. A skipped test that prints PASS is the failure
mode this effort keeps meeting; a reconciliation that silently compares
nothing is the same thing wearing a schedule.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_launch_authority.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine import canonical_boundary as cb   # noqa: E402
from compute.engine import launch_authority as la     # noqa: E402


class Skipped(Exception):
    pass


def _crontab() -> str:
    text = la.read_crontab()
    if text is None:
        raise Skipped("no crontab on this host — reconciliation needs the server")
    return text


# ── The parser is not inert ──────────────────────────────────────────────────

def test_the_generator_declares_commands():
    """If this returns nothing, every reconciliation below compares two empty
    sets and reports perfect agreement."""
    assert len(la.desired()) >= 4, la.desired()


def test_every_declared_target_resolves_to_a_real_file():
    for entry in la.desired():
        assert entry.target, f"no target parsed from {entry.raw!r}"
        assert (la.REPO / entry.target).exists(), entry.target


def test_a_module_invocation_resolves_to_its_file():
    """AlphaFive runs as `-m compute.engine.top5_strategy`, not as a path."""
    assert la._target_of("python -m compute.engine.top5_strategy --force") == \
        "backend/compute/engine/top5_strategy.py"


def test_a_shell_script_target_is_recognised():
    assert la._target_of("/opt/asx-screener/scripts/run_predictions.sh") == \
        "scripts/run_predictions.sh"


def test_a_commented_line_parses_as_disabled():
    entry = la._parse(
        "# DISABLED reason: 30 8 * * 1-5  cd /x && python backend/a/b.py", "t")
    assert entry is not None and entry.enabled is False, entry


def test_an_enabled_line_parses_as_enabled():
    entry = la._parse("30 8 * * 1-5  cd /x && python backend/a/b.py", "t")
    assert entry is not None and entry.enabled is True, entry


def test_identity_ignores_inline_reasons_but_not_cadence():
    """Comparison is semantic. A disabled entry carries a reason; that is a
    legitimate difference. A different cadence is not."""
    a = la._parse("# DISABLED because reasons: 0 9 * * 1 python backend/x.py", "t")
    b = la._parse("# 0 9 * * 1 python backend/x.py", "t")
    c = la._parse("# 0 10 * * 1 python backend/x.py", "t")
    assert a.identity == b.identity
    assert a.identity != c.identity


# ── The rules ────────────────────────────────────────────────────────────────

def test_a_canonical_touching_cron_target_is_detected():
    """top5_strategy reads screener.universe on its own Sunday schedule. If
    this stops being reported, the independent-launch rule has gone quiet."""
    found = la.independent_launches()
    assert any("top5_strategy" in f and "INDEPENDENT LAUNCH" in f
               for f in found), found


def test_pipelines_are_exempt_from_independent_launch():
    """A pipeline IS the orchestration boundary, not a step running beside
    one. Reporting it would bury the real findings."""
    found = la.independent_launches()
    for pipeline in cb.PIPELINES:
        assert not any(pipeline in f for f in found), found


def test_touches_canonical_agrees_with_the_boundary():
    """One source for "is this a dependency table". Two would drift."""
    hits = la.touches_canonical("backend/compute/engine/top5_strategy.py")
    assert set(hits) <= cb.dependency_tables()
    assert hits, "expected top5_strategy to touch canonical tables"


def test_an_unclassified_cron_target_is_reported():
    """The mutation for the classification half."""
    victim = "compute/engine/top5_strategy.py"
    saved = cb.CLASSIFICATIONS.pop(victim)
    try:
        found = la.independent_launches()
        assert any("unclassified" in f for f in found), found
    finally:
        cb.CLASSIFICATIONS[victim] = saved


# ── Reconciliation: server only ──────────────────────────────────────────────

def test_desired_and_observed_agree_on_canonical_entries():
    """The whole point. Reports drift; does not resolve it in either
    direction."""
    drift = la.reconciliation(_crontab())
    assert not drift, "\n  " + "\n  ".join(drift)


def test_observed_commands_are_visible_to_the_boundary():
    """Three canonical-relevant scripts exist only at runtime. Registering
    them is what lets the boundary judge them at all."""
    added = la.register_observed(_crontab())
    assert added, "no runtime-only canonical units registered"
    for key in added:
        assert key in cb.all_units()


def test_every_observed_canonical_unit_is_classified_or_accepted():
    la.register_observed(_crontab())
    unclassified = [v for v in cb.violations() if v.startswith("UNCLASSIFIED")]
    assert not unclassified, "\n".join(unclassified)


def test_the_runtime_disables_are_still_in_force():
    """daily_pipeline and weekly_pipeline are deliberately disabled while the
    legacy self-invalidating path has no canonical tail. If either comes back
    enabled without the orchestration landing, that is a regression of an
    operational decision, and it should fail here rather than at 08:30."""
    entries = {e.target: e for e in la.observed(_crontab())}
    for pipeline in ("daily_pipeline.py", "weekly_pipeline.py"):
        key = f"backend/scripts/eodhd/v2/jobs/{pipeline}"
        if key not in entries:
            continue
        assert not entries[key].enabled, (
            f"{pipeline} is enabled again; it revokes canonical attribution "
            f"unattended. See docs/canonical_orchestration.md")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures, skipped = [], []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Skipped as e:
            skipped.append(name)
            print(f"  SKIP  {name}  - {e}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures) - len(skipped)}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
