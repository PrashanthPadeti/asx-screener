"""
What the two copies of the signup email may contain
===================================================
`send_welcome_email` sends TWICE: once to the customer, once to the support
inbox as the new-signup notification. Until v11.2.57 both were the same
string.

That was fine while the email was a plain welcome. It stopped being fine in
v11.2.56, when the welcome and the verification email were merged: the
support copy then carried a **live verification token**, so anyone reading
that inbox could confirm a stranger's email address. Nobody decided that —
it rode along with the merge, which is exactly how a token ends up somewhere
nobody is looking for it.

These are BEHAVIOURAL tests. They call the function with the client patched
out and read what it actually tried to send, rather than reading the source
and believing it. A text matcher over email.py would have passed in v11.2.56
too, because the defect was not in the text — it was in which string was
handed to which recipient.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import app.services.email as email_mod                        # noqa: E402

TOKEN = "tok_SECRET_do_not_leak_123456"
VERIFY_URL = f"https://asxscreener.com.au/auth/verify-email?token={TOKEN}"


class _FakeResend:
    """Captures what would have been sent, instead of sending it."""

    def __init__(self):
        self.sent = []
        outer = self

        class Emails:
            @staticmethod
            def send(payload):
                outer.sent.append(payload)

        self.Emails = Emails


def _send(verify_url=None, name="Test User"):
    fake = _FakeResend()
    original = email_mod._client
    email_mod._client = lambda: fake
    try:
        email_mod.send_welcome_email("customer@example.com", name,
                                     verify_url=verify_url)
    finally:
        email_mod._client = original

    customer = [m for m in fake.sent if "customer@example.com" in m["to"]]
    support = [m for m in fake.sent if "customer@example.com" not in m["to"]]
    return customer, support


# ── The token must not reach the second mailbox ─────────────────────────────

def test_both_copies_are_sent():
    """The support copy is the new-signup notification. Losing it would make
    signups invisible without a database query."""
    customer, support = _send(verify_url=VERIFY_URL)
    assert len(customer) == 1, f"expected one customer email, got {len(customer)}"
    assert len(support) == 1, f"expected one support copy, got {len(support)}"


def test_the_customer_copy_carries_the_link():
    """The whole point of the email. Guarded here so the fix below cannot be
    'solved' by removing the link from both copies."""
    customer, _ = _send(verify_url=VERIFY_URL)
    assert TOKEN in customer[0]["html"], (
        "the customer's email has no verification link, so a new account "
        "could never be activated")


def test_the_support_copy_carries_no_token():
    """The defect this file exists for."""
    _, support = _send(verify_url=VERIFY_URL)
    assert TOKEN not in support[0]["html"], (
        "the support-inbox copy contains a live verification token; anyone "
        "reading that inbox could verify another person's email address")
    assert "verify-email" not in support[0]["html"], (
        "the support copy still contains a verification URL")


def test_the_support_copy_says_what_was_removed():
    """A copy that silently differs from what was sent is a misleading
    record. It should say the link was stripped, not just lack one."""
    _, support = _send(verify_url=VERIFY_URL)
    assert "removed from this" in support[0]["html"].lower(), (
        "the support copy drops the verification panel without saying so")


# ── One step, one button ────────────────────────────────────────────────────

def test_the_verification_email_has_exactly_one_button():
    """v11.2.56 left the old foot button in place and relabelled it, so a
    single-step email showed two identical 'Confirm my email address'
    buttons."""
    customer, _ = _send(verify_url=VERIFY_URL)
    count = customer[0]["html"].count("Confirm my email address")
    assert count == 1, (
        f"the verification email shows the confirm button {count} times; "
        f"one step deserves one call to action")


def test_the_exempt_welcome_still_has_its_button():
    """Removing the foot button for the verification case must not remove it
    from the plain welcome, where 'Start screening' is the only CTA."""
    customer, _ = _send(verify_url=None)
    html = customer[0]["html"]
    assert html.count("Start screening") == 1, (
        "the exempt welcome lost its call to action")
    assert "Confirm my email" not in html, (
        "the plain welcome asks for a verification that is not required")


def test_an_exempt_welcome_copies_identically():
    """With no token involved there is nothing to strip, so the support copy
    should remain a faithful duplicate."""
    customer, support = _send(verify_url=None)
    assert customer[0]["html"] in support[0]["html"], (
        "the support copy of a plain welcome no longer matches what the "
        "customer received")


def test_the_subject_differs_by_purpose():
    with_verify, _ = _send(verify_url=VERIFY_URL)
    without, _ = _send(verify_url=None)
    assert with_verify[0]["subject"] == (
        "Confirm your email to start using ASX Screener")
    assert without[0]["subject"] == "Welcome to ASX Screener"


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
