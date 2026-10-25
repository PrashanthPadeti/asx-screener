#!/usr/bin/env python
"""
The watchlist digest stays closed until someone opens it
========================================================
The digest was written on 6 May 2026 against `np.email_enabled`, a column
`users.notification_preferences` does not have. Every run raised
UndefinedColumn, so in five and a half months it sent nothing.

v11.2.30 repaired the column. That repair, on its own, would have started
a DAILY email at 07:30 AEST to every user holding a watchlist -- a feature
none of them have ever received, governed by `portfolio_weekly_email`, a
flag labelled *weekly*. Nobody consented to that, and nobody chose to
launch it; it would have arrived as a side effect of fixing a typo.

Fixing a dead feature is not the same act as launching it. So the digest
is gated at the same two boundaries as the anomaly alerts:

    registration   app/scheduler_registry.py does not add the job unless the flag is on
    send           send_watchlist_digests refuses even if called directly

Both are checked structurally. The alert-isolation guard was textual, and
when jobs were wrapped in `instrumented(...)` it silently stopped finding
its subject for eight releases -- so this one matches on what the code IS,
not how it is currently spelled.

Enabling this is a release decision: it needs a `watchlist_digest_email`
column, a settings field customers can see, and a deliberate first send.

Run:  python tests/test_watchlist_digest_isolation.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CONFIG = BACKEND / "app" / "core" / "config.py"
#: Registration moved to app/scheduler_registry.py in v11.2.43 so the
#: worker process can register the same jobs from the same declaration.
#: This guard FOLLOWED it. A guard left pointing at main.py would parse a
#: file with no add_job calls, find nothing to check, and pass -- which is
#: how the alert guard spent eight releases blind after jobs were wrapped
#: in instrumented().
MAIN = BACKEND / "app" / "scheduler_registry.py"
WORKER = BACKEND / "app" / "workers" / "watchlist_digest_worker.py"

FLAG = "WATCHLIST_DIGEST_ENABLED"
ENTRY = "send_watchlist_digests"


def test_the_flag_exists_and_defaults_to_off():
    """Default off is the whole control. A flag defaulting on protects
    nobody who has not already thought about it."""
    src = CONFIG.read_text(encoding="utf-8")
    assert re.search(rf"{FLAG}\s*:\s*bool\s*=\s*False", src), (
        f"{FLAG} must be declared in Settings with a default of False")
    assert not re.search(rf"{FLAG}\s*:\s*bool\s*=\s*True", src)


def test_the_job_is_not_registered_unless_the_flag_is_on():
    """The registration boundary.

    Structural: an `add_job` call mentioning the entry point anywhere in
    its arguments, which survives any further wrapping, and an enclosing
    `if` found by walking the tree rather than by counting newlines.
    """
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))

    guarded_spans = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and FLAG in {
                n.attr for n in ast.walk(node.test)
                if isinstance(n, ast.Attribute)}:
            for stmt in node.body:
                guarded_spans.append((stmt.lineno, stmt.end_lineno))

    registrations = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add_job"
        and any(isinstance(x, ast.Name) and x.id == ENTRY
                for x in ast.walk(n))]

    assert registrations, (
        f"no add_job call mentioning {ENTRY} found in app/scheduler_registry.py — the "
        f"registration has moved or been renamed, and this guard is "
        f"watching nothing")
    for call in registrations:
        assert any(start <= call.lineno <= end
                   for start, end in guarded_spans), (
            f"app/scheduler_registry.py:{call.lineno} registers {ENTRY} outside any "
            f"`if ...{FLAG}` block; the digest would send on any restart")


def test_the_worker_refuses_when_the_flag_is_off():
    """The send boundary, which does not care how it was invoked.

    Checked on the AST so that the refusal is proven to be a `return`
    inside an `if not ...FLAG` at the top of the function — not merely the
    flag's name appearing somewhere in the body.
    """
    tree = ast.parse(WORKER.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
               and n.name == ENTRY), None)
    assert fn is not None, f"{ENTRY} not found in {WORKER.name}"

    body = [s for s in fn.body
            if not (isinstance(s, ast.Expr)
                    and isinstance(s.value, ast.Constant))]
    assert body, f"{ENTRY} has no body"

    first = body[0]
    assert isinstance(first, ast.If), (
        f"the first statement of {ENTRY} is {type(first).__name__}, not a "
        f"guard; work would begin before the flag is consulted")
    assert FLAG in {n.attr for n in ast.walk(first.test)
                    if isinstance(n, ast.Attribute)}, (
        f"the first statement of {ENTRY} does not test {FLAG}")
    assert any(isinstance(n, ast.Return) for n in ast.walk(first)), (
        "the guard must return without sending")


def test_the_digest_is_not_governed_by_a_weekly_preference_alone():
    """Recorded so enabling the flag cannot quietly reuse the wrong consent.

    The query gates on portfolio_weekly_email. That is a weekly flag on a
    daily email: acceptable only while the job is off. If the flag is ever
    defaulted on, this must be a preference of the digest's own.
    """
    config = CONFIG.read_text(encoding="utf-8")
    enabled_by_default = bool(re.search(rf"{FLAG}\s*:\s*bool\s*=\s*True",
                                        config))
    body = WORKER.read_text(encoding="utf-8")
    has_own_pref = "watchlist_digest_email" in body

    if enabled_by_default and not has_own_pref:
        raise AssertionError(
            "the digest is enabled by default but still gated on "
            "portfolio_weekly_email — a weekly preference governing a daily "
            "email. Add a watchlist_digest_email column and a visible "
            "settings field before turning this on.")


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
