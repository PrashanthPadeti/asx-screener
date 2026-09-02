"""
Founding Member Offer — reminder campaign
=========================================
Sends the founding member offer reminder to free-plan users.

SAFE BY DEFAULT: this is a dry run unless you pass --send. A dry run prints the
recipient count and a sample of addresses, mints no tokens and sends nothing.

Recipients
----------
Free-plan users, excluding:
  * anyone on a paid plan (they already have it)
  * anyone who has actively unsubscribed — either marketing_emails_enabled was
    explicitly turned off via the unsubscribe link, or an audit_log entry records
    the request. Real opt-outs are honoured regardless of anything else here.
  * users with no email address

Every message carries a single-use unsubscribe token (Spam Act 2003 s.18) that
switches off marketing only — price alerts and account email keep working.

Re-running is safe: each send is logged to users.audit_log under
'campaign.founding_offer' with the send id, and anyone already logged for that
send id is skipped. So an interrupted run resumes without double-mailing.

Usage
-----
    # See who would receive it — sends nothing
    python backend/scripts/campaigns/founding_offer_reminder.py

    # Actually send
    python backend/scripts/campaigns/founding_offer_reminder.py --send

    # Send to yourself first
    python backend/scripts/campaigns/founding_offer_reminder.py --send --only you@example.com

    # Later sends in the same campaign (default send id is today's date)
    python backend/scripts/campaigns/founding_offer_reminder.py --send --send-id 2026-09-15
"""
import argparse
import json
import logging
import os
import secrets
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import psycopg2
import psycopg2.extras

from app.services.email import send_founding_offer_email          # noqa: E402
from app.core.config import settings                              # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("founding_offer")

DB_URL = os.getenv("DATABASE_URL_SYNC",
                   "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

CAMPAIGN   = "campaign.founding_offer"
FRONTEND   = (getattr(settings, "FRONTEND_URL", "") or "https://asxscreener.com.au").rstrip("/")
SEND_DELAY = 0.6          # seconds between messages — stay well inside provider limits


RECIPIENT_SQL = """
    SELECT u.id, u.email, u.name
    FROM users.users u
    WHERE u.plan = 'free'
      AND u.email IS NOT NULL AND u.email <> ''
      -- Anyone who actively opted out, plus addresses known to bounce. Resend
      -- suppresses repeat bounces anyway, but skipping them here keeps the
      -- bounce rate off our sending reputation and out of the sent count.
      AND NOT EXISTS (
            SELECT 1 FROM users.audit_log a
            WHERE a.user_id = u.id
              AND a.action IN ('prefs.unsubscribed', 'prefs.marketing_toggled',
                               'email.bounced')
      )
      AND NOT EXISTS (
            SELECT 1 FROM users.unsubscribe_tokens t
            WHERE t.user_id = u.id AND t.used = TRUE
      )
      -- Already sent this instalment
      AND NOT EXISTS (
            SELECT 1 FROM users.audit_log a
            WHERE a.user_id = u.id
              AND a.action  = %(campaign)s
              AND a.metadata->>'send_id' = %(send_id)s
      )
    ORDER BY u.created_at
"""


def mint_unsubscribe_token(cur, user_id: str) -> str:
    """Create a single-use unsubscribe token for this user."""
    token = secrets.token_urlsafe(48)
    cur.execute("""
        INSERT INTO users.unsubscribe_tokens (user_id, token, unsubscribe_type)
        VALUES (%s, %s, 'all_marketing')
    """, (user_id, token))
    return token


def log_send(cur, user_id: str, send_id: str) -> None:
    cur.execute("""
        INSERT INTO users.audit_log (user_id, action, entity_type, metadata)
        VALUES (%s, %s, 'user', %s::jsonb)
    """, (user_id, CAMPAIGN, json.dumps({"send_id": send_id, "channel": "email"})))


def main() -> None:
    ap = argparse.ArgumentParser(description="Founding member offer reminder campaign")
    ap.add_argument("--send", action="store_true",
                    help="Actually send. Without this the script is a dry run.")
    ap.add_argument("--send-id", default=date.today().isoformat(),
                    help="Identifies this instalment (default: today). Re-running "
                         "the same id skips anyone already sent it.")
    ap.add_argument("--only", help="Send to this one address only (must be an eligible recipient)")
    ap.add_argument("--test-to",
                    help="Send a single preview to any address, ignoring eligibility. "
                         "Nothing is logged and no token is minted — the unsubscribe "
                         "link is a placeholder. Use this to check the email itself.")
    ap.add_argument("--limit", type=int, help="Cap the number of recipients")
    ap.add_argument("--deadline", default="30 September 2026",
                    help="Offer end date as it appears in the email")
    args = ap.parse_args()

    # Preview — deliberately bypasses the recipient list so you can see the email
    # regardless of plan. Touches no database state.
    if args.test_to:
        log.info(f"Preview to {args.test_to} — not logged, not counted, placeholder unsubscribe link")
        ok = send_founding_offer_email(
            to_email=args.test_to,
            name="ASX Screener Admin Team",
            unsubscribe_url=f"{FRONTEND}/unsubscribe?token=PREVIEW&type=all_marketing",
            deadline=args.deadline,
        )
        log.info("Sent." if ok else "Not sent — check RESEND_API_KEY and the log above.")
        return

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute(RECIPIENT_SQL, {"campaign": CAMPAIGN, "send_id": args.send_id})
    recipients = cur.fetchall()

    if args.only:
        recipients = [r for r in recipients if r["email"].lower() == args.only.lower()]
        if not recipients:
            log.error(f"{args.only} is not in the eligible list — "
                      f"they may be on a paid plan, opted out, or already sent this instalment.")
            conn.close()
            sys.exit(1)
    if args.limit:
        recipients = recipients[:args.limit]

    log.info("─" * 62)
    log.info(f"Founding offer reminder — send id {args.send_id}")
    log.info(f"Recipients: {len(recipients):,}")
    log.info(f"Deadline in copy: {args.deadline}")
    log.info(f"Mode: {'SEND — emails will go out' if args.send else 'DRY RUN — nothing will be sent'}")
    log.info("─" * 62)

    if not recipients:
        log.info("Nobody to send to. Done.")
        conn.close()
        return

    for r in recipients[:10]:
        log.info(f"  {r['email']}  ({r['name'] or 'no name'})")
    if len(recipients) > 10:
        log.info(f"  … and {len(recipients) - 10:,} more")

    if not args.send:
        log.info("")
        log.info("Dry run — nothing sent. Add --send to deliver.")
        conn.close()
        return

    sent = failed = 0
    for i, r in enumerate(recipients, 1):
        uid = str(r["id"])
        try:
            token = mint_unsubscribe_token(cur, uid)
            url   = f"{FRONTEND}/unsubscribe?token={token}&type=all_marketing"
            ok = send_founding_offer_email(
                to_email=r["email"], name=r["name"],
                unsubscribe_url=url, deadline=args.deadline,
            )
            if ok:
                log_send(cur, uid, args.send_id)
                conn.commit()          # commit per recipient so a crash can't re-send
                sent += 1
            else:
                conn.rollback()        # no email went out — drop the unused token
                failed += 1
                log.warning(f"  not sent: {r['email']}")
        except Exception as exc:
            conn.rollback()
            failed += 1
            log.error(f"  error for {r['email']}: {exc}")

        if i % 25 == 0:
            log.info(f"  … {i:,}/{len(recipients):,}")
        time.sleep(SEND_DELAY)

    log.info("─" * 62)
    log.info(f"Sent {sent:,} · failed {failed:,}")
    log.info("Re-running with the same --send-id will retry only the failures.")
    conn.close()


if __name__ == "__main__":
    main()
