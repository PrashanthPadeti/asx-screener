#!/usr/bin/env python
"""
A paid feature that cannot run must say so, to us and not only to the customer
=============================================================================
Without `ANTHROPIC_API_KEY`, NL Screener (Pro+) and AI Portfolio Insights
(Premium+) return

    503  "AI features not configured."

to every entitled subscriber. Until v11.2.34 that was the ONLY sign:

  - no startup line saying the key was absent
  - no log when a paying customer was refused
  - nothing on /health
  - no alert

The first report came from a Premium customer, 16 days after subscribing,
in a support ticket. The system knew the whole time and told nobody.

Three properties, each checked structurally so they cannot rot into a
comment that merely describes them:

    announce    startup logs at ERROR when the key is missing
    attribute   each refusal logs, with the plan, before raising
    observe     /health reports whether the capability is available

And one it must NOT do: the key itself is never logged. A credential in a
log is a credential in every log sink, forever -- see the httpx incident in
v11.2.17, where an API key was written on every call and the rotation then
consumed its own replacement.

Run:  python tests/test_paid_features_announce_their_absence.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

AI_ROUTES = BACKEND / "app" / "api" / "v1" / "routes" / "ai.py"
MAIN = BACKEND / "app" / "main.py"
KEY = "ANTHROPIC_API_KEY"


def _guards(tree):
    """Every `if not settings.ANTHROPIC_API_KEY:` block."""
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.If)
                and isinstance(node.test, ast.UnaryOp)
                and isinstance(node.test.op, ast.Not)
                and KEY in {n.attr for n in ast.walk(node.test)
                            if isinstance(n, ast.Attribute)}):
            out.append(node)
    return out


def test_every_refusal_is_attributed_before_it_is_raised():
    """A 503 with no server-side record is how this survived 16 days."""
    tree = ast.parse(AI_ROUTES.read_text(encoding="utf-8"))
    guards = _guards(tree)
    assert len(guards) >= 2, (
        f"expected at least 2 AI key guards in ai.py, found {len(guards)}; "
        f"the endpoints have moved and this test is watching nothing")

    for g in guards:
        calls = [n for n in ast.walk(g) if isinstance(n, ast.Call)]
        logged = any(isinstance(c.func, ast.Attribute)
                     and c.func.attr in ("error", "warning")
                     for c in calls)
        raised = any(isinstance(n, ast.Raise) for n in ast.walk(g))
        assert logged, (
            f"ai.py:{g.lineno} refuses a paying subscriber without logging "
            f"anything; the 503 reaches the customer and nobody else")
        assert raised, f"ai.py:{g.lineno} logs but does not refuse"


def test_startup_announces_a_missing_key():
    """Absence must be stated once at boot, not inferred from traffic."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    guards = _guards(tree)
    assert guards, (
        f"app/main.py does not check {KEY} at startup; a paid feature can be "
        f"entirely off with nothing said until a customer reports it")
    assert any(
        isinstance(c.func, ast.Attribute) and c.func.attr == "error"
        for g in guards for c in ast.walk(g) if isinstance(c, ast.Call)), (
        "the startup check does not log at ERROR. People are being charged "
        "for a feature that cannot run; that is not an informational notice.")


def test_health_reports_whether_the_capability_is_available():
    src = MAIN.read_text(encoding="utf-8")
    assert "ai_configured" in src, (
        "/health does not report AI availability, so there is no way to ask "
        "the running process whether paid features work")
    assert re.search(r'"ai_configured":\s*bool\(', src), (
        "ai_configured must be a bool() of the key's presence -- not the key, "
        "not its length, not a prefix")


def test_the_key_is_never_logged():
    """Secrets at the sink. A credential in a log is in every log sink."""
    offenders = []
    for path in (AI_ROUTES, MAIN):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("debug", "info", "warning",
                                           "error", "exception", "critical")):
                continue
            for arg in ast.walk(node):
                if isinstance(arg, ast.Attribute) and arg.attr == KEY:
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        f"the API key is passed to a log call at {offenders}. Log whether a "
        f"key is present, never the key.")


def test_the_refusal_names_the_plan():
    """So the log says who was refused, not merely that someone was."""
    src = AI_ROUTES.read_text(encoding="utf-8")
    assert re.search(r'log\.error\([^)]*[Pp]lan', src, re.S), (
        "the refusal log does not record the subscriber's plan; without it "
        "the line cannot distinguish a free user probing a paid endpoint "
        "from a Premium customer being denied what they bought")


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
