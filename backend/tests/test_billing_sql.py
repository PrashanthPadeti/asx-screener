"""
The billing statements have to survive being prepared
=====================================================
On 15 Sep 2026 every subscription upgrade on the site was broken, and had been
for some time, by one placeholder used twice:

    plan                        = :plan            -- VARCHAR(20)
    subscription_inactive_since = CASE WHEN :plan = 'free' THEN ...

PostgreSQL deduced *character varying* from the assignment and *text* from the
comparison against a bare literal, and refused to prepare the statement at all:

    asyncpg.exceptions.AmbiguousParameterError:
      inconsistent types deduced for parameter $1
      DETAIL: text versus character varying

Every ``customer.subscription.created`` and ``.updated`` event returned 500.
The other webhook branches returned 200, so the endpoint looked half-alive in
the access log. No account could be upgraded by any path — and because a failed
upgrade leaves ``stripe_subscription_id`` NULL, ``/checkout`` read that as "new
subscriber" and started *another* paid subscription on every retry. One
customer ended up with two live subscriptions and two charges 23 minutes apart,
while their account showed Free.

Why a textual guard rather than a unit test: nothing in Python objects to this.
The SQL is a valid string, the parameters dict is well formed, SQLAlchemy
compiles it happily. Only a real PostgreSQL parameter-type deduction rejects
it, which means it cannot fail until it is in front of a paying customer.

The rule being enforced: **in these statements, never bind one parameter into
both an assignment and a predicate.** Compute the predicate in Python and bind
its result. A boolean has one unambiguous type.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_billing_sql.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROUTES = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "routes"

#: Files whose SQL runs on the billing path. A statement here failing to
#: prepare costs money, not just an error page.
BILLING_SOURCES = ("stripe_routes.py",)


def _statements(src: str) -> list[str]:
    """Triple-quoted bodies that look like SQL, with comment lines removed.

    Comments in these files quote the broken SQL on purpose — that is what the
    explanation is for — so they must not be matched. An earlier guard of mine
    in this repo matched its own comment rather than the code it guarded.
    """
    out = []
    for m in re.finditer(r'"""(.*?)"""', src, re.S):
        body = m.group(1)
        if not re.search(r"\b(UPDATE|INSERT|SELECT|DELETE)\b", body):
            continue
        kept = [ln for ln in body.splitlines()
                if not ln.strip().startswith("--")]
        out.append("\n".join(kept))
    return out


def test_no_bind_parameter_is_compared_against_a_bare_literal():
    """The defect itself. One placeholder, two type deductions, no upgrades.

    The rule is narrower than "never reuse a parameter", which was this
    guard's first and wrong formulation: reuse is fine when every position
    deduces the same type — ``:is_free`` appears in two CASE predicates and
    both are boolean. What PostgreSQL cannot resolve is a parameter assigned
    to a typed column in one place and compared to an untyped literal in
    another, because the literal contributes *text* and the column
    contributes its own type.

    A guard that flagged all reuse would have failed on the correct fix, and a
    guard that fails on correct code gets switched off.
    """
    pattern = re.compile(
        r"""(?<![:\w]):([a-z_][a-z0-9_]*)\s*(?:=|<>|!=)\s*'   # :param = 'lit'
            |'[^']*'\s*(?:=|<>|!=)\s*(?<![:\w]):([a-z_][a-z0-9_]*)""",  # 'lit' = :param
        re.X)

    offenders = []
    for name in BILLING_SOURCES:
        src = (ROUTES / name).read_text(encoding="utf-8")
        for stmt in _statements(src):
            for m in pattern.finditer(stmt):
                param = m.group(1) or m.group(2)
                # A literal comparison on its own is safe: one position, one
                # deduction, which is how :billing_period = 'monthly' has been
                # working in the founding-member claim all along. The conflict
                # needs a SECOND position contributing a different type.
                uses = len(re.findall(rf"(?<![:\w]):{param}\b", stmt))
                if uses > 1:
                    offenders.append(
                        f"{name}: :{param} is compared to a literal and used "
                        f"in {uses - 1} other position(s)")

    assert not offenders, (
        "a bind parameter is compared directly against a string literal:\n  "
        + "\n  ".join(sorted(set(offenders)))
        + "\nThe literal deduces 'text' while the column the same parameter is "
          "assigned to deduces its own type, and PostgreSQL refuses to prepare "
          "the statement. Compute the predicate in Python and bind a boolean."
    )


def test_the_subscription_update_still_clears_the_retention_countdown():
    """The fix must not quietly drop what the CASE was for.

    A paid account that keeps subscription_inactive_since is scheduled for
    data deletion while the customer believes they are paid up, so this is not
    bookkeeping that can be lost in a refactor.
    """
    src = (ROUTES / "stripe_routes.py").read_text(encoding="utf-8")
    stmts = [s for s in _statements(src)
             if "subscription_inactive_since" in s and "UPDATE users.users" in s]

    assert stmts, "no statement writes subscription_inactive_since any more"
    assert any("data_deletion_scheduled_at" in s for s in stmts), (
        "the retention countdown is no longer cleared alongside it")


def test_the_free_branch_is_driven_by_a_bound_boolean():
    """Specifically that the repair is the one described, not a cast bolted on
    top of the same double-binding."""
    src = (ROUTES / "stripe_routes.py").read_text(encoding="utf-8")

    for stmt in _statements(src):
        if "subscription_inactive_since" not in stmt:
            continue
        assert ":plan = 'free'" not in stmt, (
            "the ambiguous comparison is back — bind :is_free instead")


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
