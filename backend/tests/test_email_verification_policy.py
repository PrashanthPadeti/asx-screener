"""
Mandatory email verification, and who it must never touch
=========================================================
New accounts must verify their email before they can sign in. Existing
accounts must NOT be affected — and that is the property this file exists to
protect, because getting it wrong locks paying customers out of something
they already bought.

The background matters. Until 26 Oct 2026 registration sent a welcome email
and no verification email at all; the only way an account ever received one
was an admin triggering it by hand. So every unverified account at the time
this policy was introduced — a Pro subscriber among them — is unverified
because nobody asked. The cutoff is what keeps the rule from punishing them
for our omission.

Three things are checked:

  the RULE          who it applies to, at dates either side of the cutoff
  the DELIVERY      registration actually sends the email the gate demands
  the ESCAPE HATCH  an unverified user can get the link resent
"""

import ast
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.verification_policy import verification_required_for  # noqa: E402

AUTH = BACKEND / "app" / "api" / "v1" / "routes" / "auth.py"
CUTOFF = "2026-10-27"
BEFORE = datetime(2026, 10, 26, 23, 59, tzinfo=timezone.utc)
AFTER = datetime(2026, 10, 27, 0, 1, tzinfo=timezone.utc)


def _auth_src() -> str:
    return AUTH.read_text(encoding="utf-8")


# ── The rule ────────────────────────────────────────────────────────────────

def test_an_existing_account_is_never_required_to_verify():
    """The property that protects paying customers.

    Brett MacRae (Pro, active, email_verified = False) registered 22 Oct 2026
    and must keep signing in exactly as before.
    """
    brett_joined = datetime(2026, 10, 22, 4, 24, tzinfo=timezone.utc)
    assert verification_required_for(brett_joined, CUTOFF) is False
    assert verification_required_for(BEFORE, CUTOFF) is False
    # Years earlier, for good measure.
    assert verification_required_for(
        datetime(2026, 5, 3, tzinfo=timezone.utc), CUTOFF) is False


def test_a_new_account_must_verify():
    assert verification_required_for(AFTER, CUTOFF) is True
    assert verification_required_for(
        datetime(2027, 1, 1, tzinfo=timezone.utc), CUTOFF) is True


def test_the_boundary_is_inclusive_of_the_cutoff_day():
    """On-or-after, so the cutoff date itself is covered. Stated as a test
    because 'from the 27th' is ambiguous in English and not in code."""
    assert verification_required_for(
        datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc), CUTOFF) is True


def test_a_naive_timestamp_is_treated_as_utc():
    """created_at can come back without a timezone depending on the driver.
    Comparing naive to aware raises, which would surface as a 500 on login."""
    assert verification_required_for(datetime(2026, 10, 28), CUTOFF) is True
    assert verification_required_for(datetime(2026, 10, 20), CUTOFF) is False


def test_an_empty_cutoff_disables_the_policy():
    assert verification_required_for(AFTER, "") is False
    assert verification_required_for(AFTER, "   ") is False


def test_a_malformed_cutoff_fails_open():
    """It must not lock every new user out of an account they just created.

    Fail-open is the right direction here and only here: the cost of a
    missed verification is an unverified address, the cost of a wrong
    lockout is a customer who cannot use what they paid for.
    """
    assert verification_required_for(AFTER, "not-a-date") is False
    assert verification_required_for(AFTER, "27/10/2026") is False


def test_a_missing_created_at_is_treated_as_pre_existing():
    assert verification_required_for(None, CUTOFF) is False


# ── Delivery: the gate is only honest if the email is actually sent ────────

def test_registration_sends_a_verification_email():
    """Before this policy, registration sent a welcome email and nothing
    else. Blocking login without this line would strand every new signup at
    a wall, with no email to find in any folder."""
    src = _auth_src()
    reg = src[src.index('@router.post("/register"'):src.index('# ── Login')]
    assert "_issue_verification_email" in reg, (
        "registration does not send a verification email, so the login gate "
        "would lock out users who were never sent a link")


def test_registration_issues_no_tokens_when_verification_is_required():
    """Otherwise the new user is handed a session and never meets the gate."""
    src = _auth_src()
    reg = src[src.index('@router.post("/register"'):src.index('# ── Login')]
    guard = reg.index("_verification_required_for")
    after = reg[guard:]
    returned = after[:after.index("return") + 200]
    assert "_token_response" not in returned, (
        "registration returns tokens on the verification-required path; the "
        "login gate would be decorative")


# ── The gate ────────────────────────────────────────────────────────────────

def test_verification_is_checked_after_the_password():
    """Checking it first would make this an account-enumeration oracle:
    an attacker could learn which addresses exist by watching which answer
    403 rather than 401."""
    src = _auth_src()
    login = src[src.index('@router.post("/login"'):]
    pw = login.index("Invalid email or password")
    gate = login.index("email_not_verified")
    assert pw < gate, (
        "the verification check runs before the password check — unverified "
        "accounts would be identifiable without valid credentials")


def test_the_refusal_names_the_cause_and_mentions_spam():
    """A generic 'login failed' sends people to reset their password."""
    src = _auth_src()
    assert "email_not_verified" in src, "no machine-readable code for the UI"
    block = src[src.index("email_not_verified"):]
    block = block[:1200]
    assert "spam" in block.lower(), (
        "the refusal does not mention the spam folder, which is where the "
        "message most often is")


# ── The escape hatch ────────────────────────────────────────────────────────

def test_an_unverified_user_can_request_the_link_again():
    """Mandatory verification without a resend is a trap: an email deleted
    from spam would lock the account permanently."""
    src = _auth_src()
    assert '@router.post("/resend-verification"' in src, (
        "no way for a locked-out user to get the verification link resent")


def test_resend_does_not_reveal_whether_an_account_exists():
    """It needs no authentication, so a different answer for a registered
    address turns it into an enumeration oracle.

    By AST, not by text. The first version of this test asserted that the
    string "404" did not appear in the function — and failed, because it
    matched the COMMENT explaining why a 404 would be wrong. A text matcher
    reads its own documentation.
    """
    tree = ast.parse(_auth_src(), str(AUTH))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
               and n.name == "resend_verification"), None)
    assert fn is not None, "resend_verification is gone"

    # No raise at all: every path must return the same body. A raise is how
    # a differential answer gets introduced.
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert not raises, (
        f"resend_verification raises on {len(raises)} path(s); any error "
        f"response distinguishes registered addresses from unregistered ones")

    # And every return is the same name.
    returned = [n.value for n in ast.walk(fn) if isinstance(n, ast.Return)]
    names = {getattr(r, "id", None) for r in returned}
    assert names == {"same_answer"}, (
        f"resend_verification returns {names}; every path must return the "
        f"identical response or the differences reveal which emails exist")


def test_resend_is_rate_limited_and_cooled_down():
    """Otherwise it is a mailbomb aimed at any address."""
    src = _auth_src()
    fn = src[src.index('@limiter.limit("3/minute")'):]
    fn = fn[:fn.index('@router.get("/verify-email"')]
    assert "resend-verification" in fn, "the rate limit is not on resend"
    assert "timedelta(minutes=" in fn, "no per-address cooldown"


def test_a_new_signup_receives_one_email_not_two():
    """Two emails seconds apart contradicted each other.

    The welcome said "thanks for joining, start screening" while the account
    could not be used until the verification link was clicked — inviting the
    new user to do something that would have failed. Registration now sends
    ONE verification-led email with the welcome content underneath.
    """
    src = _auth_src()
    reg = src[src.index('@router.post("/register"'):src.index('# ── Login')]
    # The verification branch must not ALSO send a bare welcome.
    # The verification branch runs from the guard to its own `return`; the
    # exempt path follows it and SHOULD send a plain welcome, so slicing to
    # the end of the function cannot tell them apart.
    guard = reg.index("_verification_required_for")
    branch_end = reg.index("return {", guard)
    verification_branch = reg[guard:branch_end]

    assert "welcome=True" in verification_branch, (
        "the verification path does not send the combined welcome+verify "
        "email")
    assert "send_welcome_email(body.email" not in verification_branch, (
        "the verification path still sends a separate welcome email; a new "
        "signup would receive two contradicting messages")
    # And the welcome that remains must belong to the exempt path, below.
    assert reg.index("send_welcome_email(body.email") > branch_end, (
        "a bare welcome is sent before the verification branch, so every "
        "new signup gets it regardless")


def test_an_exempt_signup_still_gets_a_welcome():
    """Verification off, or an account created before the cutoff — the plain
    welcome stands alone and 'start screening' is true advice."""
    src = _auth_src()
    reg = src[src.index('@router.post("/register"'):src.index('# ── Login')]
    assert "send_welcome_email(body.email" in reg, (
        "an exempt signup receives no welcome email at all")


def test_the_combined_email_leads_with_verification():
    """The first thing a new user reads should be the thing they must do."""
    email_src = (BACKEND / "app" / "services" / "email.py").read_text(
        encoding="utf-8")
    start = email_src.index("def send_welcome_email")
    nxt = email_src.find("\ndef ", start + 10)
    fn = email_src[start:nxt if nxt != -1 else len(email_src)]
    assert "verify_url" in fn, "send_welcome_email cannot carry a verify link"
    assert "spam" in fn.lower(), (
        "the combined email does not mention the spam folder, which is where "
        "it most often is")
    # The verification panel must come before the feature sections.
    assert fn.index("verify_block") < fn.index("Start screening"), (
        "the verification step is not the first thing in the email")


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
