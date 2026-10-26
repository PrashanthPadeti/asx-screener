"""
Who must verify their email before they can sign in
===================================================
Mandatory email verification applies ONLY to accounts created on or after
`settings.EMAIL_VERIFICATION_REQUIRED_FROM`. Everyone who registered earlier
is exempt, permanently.

The cutoff is the whole point. Until 26 Oct 2026 registration sent a welcome
email and no verification email at all — the only way an account ever got one
was an admin triggering it by hand. So every existing unverified account,
including paying subscribers, is unverified because nobody ever asked them.
Applying the rule retroactively would lock customers out of something they
paid for, to fix an omission that was ours.

Kept in its own module, free of FastAPI and database imports, so the rule can
be tested directly rather than through the application.
"""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def verification_required_for(created_at, cutoff_raw: str | None = None) -> bool:
    """True when this account must verify before it can sign in.

    `cutoff_raw` is injectable so the rule can be exercised at dates other
    than today's configuration — a test that can only run against the live
    setting is a test of the setting, not of the rule.
    """
    if cutoff_raw is None:
        # Imported here, not at module scope, so the rule itself can be
        # exercised without pydantic, a database or any configuration. A
        # test that must boot the application to check a date comparison is
        # a test that will eventually be skipped.
        from app.core.config import settings
        cutoff_raw = settings.EMAIL_VERIFICATION_REQUIRED_FROM
    raw = (cutoff_raw or "").strip()

    # Empty disables the policy: the behaviour that existed before it.
    if not raw:
        return False

    try:
        cutoff = datetime.fromisoformat(raw)
    except ValueError:
        # Fail OPEN, and say so. A malformed date must not lock every new
        # user out of an account they just created; silence would leave the
        # policy off with nothing reporting it.
        log.error(
            "EMAIL_VERIFICATION_REQUIRED_FROM=%r is not an ISO date — email "
            "verification is NOT being enforced. Fix the value in config.",
            raw)
        return False

    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    # An account with no creation timestamp predates the column, so it
    # predates the policy.
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return created_at >= cutoff
