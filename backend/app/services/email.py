"""
ASX Screener — Email Service (Resend)
========================================
Thin wrapper around the Resend SDK.
Falls back to a no-op log if RESEND_API_KEY is not configured.
"""
import logging
from html import escape as html_escape
from typing import Optional

from app.core.config import settings

log = logging.getLogger(__name__)


def _client():
    """Return a configured Resend client, or None if key not set."""
    if not settings.RESEND_API_KEY:
        return None
    import resend
    resend.api_key = settings.RESEND_API_KEY
    return resend


def send_alert_email(
    to_email: str,
    asx_code: str,
    alert_type: str,
    threshold: float,
    current_value: float,
    company_name: Optional[str] = None,
) -> bool:
    """
    Send a price-alert triggered email.
    Returns True on success, False on failure / no-op.
    """
    resend = _client()
    if resend is None:
        log.info(f"[email no-op] Alert triggered: {asx_code} {alert_type} {threshold} (current: {current_value})")
        return False

    label = company_name or asx_code
    direction = "rose above" if "above" in alert_type else "fell below"

    if "pct_change" in alert_type:
        subject  = f"ASX Alert: {asx_code} moved {current_value:+.2f}%"
        body_txt = (
            f"{label} ({asx_code}) has moved {current_value:+.2f}% today, "
            f"crossing your alert threshold of {threshold:+.2f}%."
        )
    else:
        subject  = f"ASX Alert: {asx_code} {direction} ${threshold:.3f}"
        body_txt = (
            f"{label} ({asx_code}) has {direction} your alert price of ${threshold:.3f}. "
            f"Current price: ${current_value:.3f}."
        )

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8;margin-bottom:4px">⚡ ASX Alert Triggered</h2>
      <p style="font-size:18px;font-weight:600;margin:8px 0">{asx_code} — {label}</p>
      <p style="color:#374151">{body_txt}</p>
      <a href="http://asxscreener.com.au/company/{asx_code}"
         style="display:inline-block;margin-top:16px;padding:10px 20px;
                background:#2563eb;color:white;border-radius:8px;text-decoration:none">
        View {asx_code}
      </a>
      <hr style="margin-top:32px;border-color:#e5e7eb"/>
      <p style="font-size:12px;color:#9ca3af">
        ASX Screener · <a href="http://asxscreener.com.au/alerts">Manage alerts</a>
      </p>
    </div>
    """

    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [to_email],
            "subject": subject,
            "html":    html,
        })
        log.info(f"Alert email sent to {to_email} for {asx_code}")
        return True
    except Exception as e:
        log.error(f"Failed to send alert email: {e}")
        return False


def send_support_notification(
    ticket_number: int,
    name: str,
    email: str,
    phone: Optional[str],
    category: str,
    subject: str,
    description: str,
    user_id: Optional[str] = None,
    context_url: Optional[str] = None,
    context_user_agent: Optional[str] = None,
    context_viewport: Optional[str] = None,
    context_timestamp: Optional[str] = None,
    subscription_tier: Optional[str] = None,
) -> bool:
    """Send a new support ticket notification to the support team."""
    resend = _client()
    support_to = settings.SUPPORT_EMAIL

    cat_label = category.replace("_", " ").title()
    tier_label = (subscription_tier or "—").replace("_", " ").title()

    # Build optional context rows
    ctx_rows = ""
    if context_url:
        ctx_rows += f'<tr><td style="padding:4px 0;color:#6b7280;width:120px">URL</td><td style="padding:4px 0;font-size:12px;word-break:break-all;color:#374151">{context_url}</td></tr>'
    if context_user_agent:
        ctx_rows += f'<tr><td style="padding:4px 0;color:#6b7280">Browser</td><td style="padding:4px 0;font-size:11px;color:#6b7280">{context_user_agent}</td></tr>'
    if context_viewport:
        ctx_rows += f'<tr><td style="padding:4px 0;color:#6b7280">Viewport</td><td style="padding:4px 0;font-size:12px;color:#374151">{context_viewport}</td></tr>'
    if context_timestamp:
        ctx_rows += f'<tr><td style="padding:4px 0;color:#6b7280">Submitted</td><td style="padding:4px 0;font-size:12px;color:#374151">{context_timestamp}</td></tr>'

    context_block = ""
    if ctx_rows:
        context_block = f"""
      <div style="margin-top:16px;padding:16px;background:#f0f9ff;border-radius:8px;border:1px solid #bae6fd">
        <p style="margin:0 0 8px;font-size:11px;font-weight:600;color:#0369a1;text-transform:uppercase;letter-spacing:0.05em">Browser context</p>
        <table style="width:100%;border-collapse:collapse">{ctx_rows}</table>
      </div>"""

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8;margin-bottom:4px">🎫 New Support Ticket #{ticket_number}</h2>
      <table style="width:100%;border-collapse:collapse;margin-top:16px">
        <tr><td style="padding:6px 0;color:#6b7280;width:120px">Category</td>
            <td style="padding:6px 0;font-weight:600">{cat_label}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280">Subject</td>
            <td style="padding:6px 0;font-weight:600">{subject}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280">From</td>
            <td style="padding:6px 0">{name} &lt;{email}&gt;</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280">Phone</td>
            <td style="padding:6px 0">{phone or '—'}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280">Plan</td>
            <td style="padding:6px 0">{tier_label}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280">User ID</td>
            <td style="padding:6px 0;font-size:12px;color:#9ca3af">{user_id or 'Not logged in'}</td></tr>
      </table>
      <div style="margin-top:16px;padding:16px;background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb">
        <p style="margin:0;white-space:pre-wrap;color:#374151">{description}</p>
      </div>
      {context_block}
      <a href="https://asxscreener.com.au/admin/support"
         style="display:inline-block;margin-top:16px;padding:10px 20px;
                background:#2563eb;color:white;border-radius:8px;text-decoration:none">
        View in Admin Panel
      </a>
    </div>
    """
    if resend is None:
        log.info(f"[email no-op] Support ticket #{ticket_number}: {subject} from {email}")
        return False
    try:
        resend.Emails.send({
            "from":     settings.EMAIL_FROM,
            "to":       [support_to],
            "reply_to": email,
            "subject":  f"[Ticket #{ticket_number}] {subject}",
            "html":     html,
        })
        log.info(f"Support notification sent for ticket #{ticket_number}")
        return True
    except Exception as e:
        log.error(f"Failed to send support notification: {e}")
        return False


def send_support_confirmation(
    ticket_number: int,
    name: str,
    email: str,
    category: str,
    subject: str,
) -> bool:
    """Send a confirmation email to the user after they submit a support ticket."""
    resend = _client()
    greeting = f"Hi {name}," if name else "Hi,"
    cat_label = category.replace("_", " ").title()
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8;margin-bottom:4px">✅ Support request received</h2>
      <p style="color:#374151">{greeting}</p>
      <p style="color:#374151">
        Thanks for reaching out. We've received your support request and will get back to you
        within <strong>1 business day</strong>.
      </p>
      <div style="margin:20px 0;padding:16px;background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb">
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <td style="padding:5px 0;color:#6b7280;width:120px">Reference</td>
            <td style="padding:5px 0;font-weight:700;color:#111827">#{ticket_number}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280">Category</td>
            <td style="padding:5px 0;color:#374151">{cat_label}</td>
          </tr>
          <tr>
            <td style="padding:5px 0;color:#6b7280">Subject</td>
            <td style="padding:5px 0;color:#374151">{subject}</td>
          </tr>
        </table>
      </div>
      <p style="color:#374151">
        Please keep your reference number <strong>#{ticket_number}</strong> handy.
        Our team will reply directly to this email address.
      </p>
      <p style="font-size:13px;color:#6b7280">
        If you didn't submit this request, you can safely ignore this email.
      </p>
      <hr style="margin-top:32px;border-color:#e5e7eb"/>
      <p style="font-size:12px;color:#9ca3af">
        ASX Screener ·
        <a href="https://asxscreener.com.au" style="color:#9ca3af">asxscreener.com.au</a>
      </p>
    </div>
    """
    if resend is None:
        log.info(f"[email no-op] Support confirmation #{ticket_number} to {email}")
        return False
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [email],
            "subject": f"[Ticket #{ticket_number}] We received your support request — ASX Screener",
            "html":    html,
        })
        log.info(f"Support confirmation sent to {email} for ticket #{ticket_number}")
        return True
    except Exception as e:
        log.error(f"Failed to send support confirmation to {email}: {e}")
        return False


def send_support_resolution(
    ticket_number: int,
    name: str,
    email: str,
    subject: str,
    resolution_notes: str,
    status: str = "resolved",
) -> bool:
    """Send the support team's resolution to the user when a ticket is resolved/closed."""
    resend = _client()
    greeting = f"Hi {name}," if name else "Hi,"
    heading  = "✅ Your support request has been resolved" if status == "resolved" \
               else "Your support request has been closed"

    # resolution_notes is plain text typed by an admin — escape it and keep line breaks.
    notes_html = html_escape(resolution_notes or "").replace("\n", "<br/>")

    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8;margin-bottom:4px">{heading}</h2>
      <p style="color:#374151">{greeting}</p>
      <p style="color:#374151">
        We've updated your support request <strong>#{ticket_number}</strong>
        ({html_escape(subject)}).
      </p>
      <div style="margin:20px 0;padding:16px;background:#f9fafb;border-radius:8px;border:1px solid #e5e7eb">
        <p style="margin:0 0 6px;color:#6b7280;font-size:13px">Resolution</p>
        <p style="margin:0;color:#111827;line-height:1.5">{notes_html}</p>
      </div>
      <p style="color:#374151">
        If this doesn't fully answer your question, just reply to this email and we'll pick it
        up again — please keep <strong>#{ticket_number}</strong> in the subject line.
      </p>
      <hr style="margin-top:32px;border-color:#e5e7eb"/>
      <p style="font-size:12px;color:#9ca3af">
        ASX Screener ·
        <a href="https://asxscreener.com.au" style="color:#9ca3af">asxscreener.com.au</a>
      </p>
    </div>
    """
    if resend is None:
        log.info(f"[email no-op] Support resolution #{ticket_number} to {email}")
        return False
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [email],
            "subject": f"[Ticket #{ticket_number}] {subject} — resolved",
            "html":    html,
        })
        log.info(f"Support resolution sent to {email} for ticket #{ticket_number}")
        return True
    except Exception as e:
        log.error(f"Failed to send support resolution to {email}: {e}")
        return False


def send_password_reset_email(to_email: str, reset_url: str, name: Optional[str] = None) -> bool:
    """Send a password reset link email."""
    resend = _client()
    if resend is None:
        log.info(f"[email no-op] Password reset for {to_email}: {reset_url}")
        return False

    greeting = f"Hi {name}," if name else "Hi,"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8;margin-bottom:4px">Reset your password</h2>
      <p>{greeting}</p>
      <p style="color:#374151">We received a request to reset your ASX Screener password.
         Click the button below — this link expires in 1 hour.</p>
      <a href="{reset_url}"
         style="display:inline-block;margin-top:16px;padding:12px 24px;
                background:#2563eb;color:white;border-radius:8px;text-decoration:none;font-weight:600">
        Reset Password
      </a>
      <p style="margin-top:24px;font-size:13px;color:#6b7280">
        If you didn't request this, you can safely ignore this email.
        Your password won't change until you click the link above.
      </p>
      <hr style="margin-top:32px;border-color:#e5e7eb"/>
      <p style="font-size:12px;color:#9ca3af">ASX Screener · asxscreener.com.au</p>
    </div>
    """
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [to_email],
            "subject": "Reset your ASX Screener password",
            "html":    html,
        })
        log.info(f"Password reset email sent to {to_email}")
        return True
    except Exception as e:
        log.error(f"Failed to send password reset email: {e}")
        return False


def send_verification_reminder_email(to_email: str, verify_url: str, name: Optional[str] = None) -> bool:
    """Send an email-verification reminder with a one-click verify link."""
    resend = _client()
    if resend is None:
        log.info(f"[email no-op] Verification reminder for {to_email}: {verify_url}")
        return False

    greeting = f"Hi {name}," if name else "Hi,"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8;margin-bottom:4px">Verify your email address</h2>
      <p>{greeting}</p>
      <p style="color:#374151">
        You're almost set! Please verify your email address to unlock all features
        of ASX Screener — including price alerts, watchlist digests, and weekly summaries.
      </p>
      <a href="{verify_url}"
         style="display:inline-block;margin-top:16px;padding:12px 24px;
                background:#2563eb;color:white;border-radius:8px;
                text-decoration:none;font-weight:600">
        Verify My Email
      </a>
      <p style="margin-top:24px;font-size:13px;color:#6b7280">
        This link expires in 48 hours. If you didn't create an ASX Screener account,
        you can safely ignore this email.
      </p>
      <hr style="margin-top:32px;border-color:#e5e7eb"/>
      <p style="font-size:12px;color:#9ca3af">
        ASX Screener · <a href="https://asxscreener.com.au">asxscreener.com.au</a>
      </p>
    </div>
    """
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [to_email],
            "subject": "Verify your ASX Screener email address",
            "html":    html,
        })
        log.info(f"Verification reminder sent to {to_email}")
        return True
    except Exception as e:
        log.error(f"Failed to send verification reminder to {to_email}: {e}")
        return False


def send_welcome_email(to_email: str, name: Optional[str] = None) -> bool:
    """
    Welcome a new user, and copy the same email to the support inbox so signups
    are visible without checking the database.
    """
    resend = _client()
    greeting = f"Hi {html_escape(name)}," if name else "Hi,"

    def _section(title: str, blurb: str, items: list[str]) -> str:
        lis = "".join(
            f'<li style="margin:4px 0;color:#374151">{i}</li>' for i in items
        )
        return f"""
        <div style="margin:22px 0">
          <h3 style="margin:0 0 4px;font-size:15px;color:#111827">{title}</h3>
          <p style="margin:0 0 8px;font-size:13px;color:#6b7280">{blurb}</p>
          <ul style="margin:0;padding-left:18px;font-size:14px">{lis}</ul>
        </div>
        """

    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8;margin-bottom:4px">Welcome to ASX Screener</h2>
      <p style="color:#374151">{greeting}</p>
      <p style="color:#374151">
        Thanks for joining. ASX Screener is built specifically for the Australian
        market &mdash; franking credits, mining and A-REIT metrics, and ASIC short
        data you won't find in a tool adapted from the US. Here's what you can do.
      </p>

      {_section(
        "Screen",
        "Find the companies worth a closer look.",
        [
          "Filter 2,100+ ASX-listed companies across 300+ metrics in 15 categories",
          "30+ ready-made screens &mdash; value, quality, momentum, dividend income and more",
          "Grossed-up yields with full franking credit calculations",
          "Save any screen and re-run it whenever you like",
        ])}

      {_section(
        "Analyse",
        "Understand a company before you commit.",
        [
          "Company pages with fundamentals, ratios, financials and charts",
          "Piotroski F-Score and Altman Z-Score on every stock",
          "Mining depth (AISC, reserve life) and A-REIT metrics (NTA, WALE, occupancy)",
          "ASIC daily short positions, updated with the market",
        ])}

      {_section(
        "Search &amp; track",
        "Stay across the names you care about.",
        [
          "Search any ASX code or company name from anywhere in the app",
          "Watchlists synced across your devices",
          "Price and percentage-change alerts delivered by email",
          "AlphaFive &mdash; our weekly algo-ranked top 5 from the ASX 200",
        ])}

      <a href="https://asxscreener.com.au/screener"
         style="display:inline-block;margin-top:8px;padding:11px 22px;
                background:#2563eb;color:white;border-radius:8px;
                text-decoration:none;font-weight:600">
        Start screening
      </a>

      <p style="margin-top:24px;font-size:13px;color:#6b7280">
        Not sure where to begin? Open the screener and pick a Quick Screen &mdash;
        it fills in the filters for you. Any questions, just reply to this email
        or use the <a href="https://asxscreener.com.au/contact"
        style="color:#2563eb">contact form</a>.
      </p>

      <hr style="margin-top:28px;border:none;border-top:1px solid #e5e7eb"/>
      <p style="font-size:11px;color:#9ca3af;line-height:1.5">
        ASX Screener provides information and educational tools only. Nothing here
        is financial advice or a recommendation to buy or sell any security.
        Always do your own research.<br/>
        <a href="https://asxscreener.com.au" style="color:#9ca3af">asxscreener.com.au</a>
      </p>
    </div>
    """

    if resend is None:
        log.info(f"[email no-op] Welcome email for {to_email}")
        return False

    sent = False
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [to_email],
            "subject": "Welcome to ASX Screener",
            "html":    html,
        })
        log.info(f"Welcome email sent to {to_email}")
        sent = True
    except Exception as e:
        log.error(f"Failed to send welcome email to {to_email}: {e}")

    # Copy to the support inbox — doubles as the new-signup notification.
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [settings.SUPPORT_EMAIL],
            "subject": f"New signup: {to_email}",
            "html": (
                f'<p style="font-family:sans-serif;font-size:13px;color:#6b7280">'
                f'New account created &mdash; <strong>{html_escape(name or "(no name)")}'
                f'</strong> &lt;{html_escape(to_email)}&gt;. '
                f'Copy of the welcome email below.</p><hr/>' + html
            ),
        })
    except Exception as e:
        log.error(f"Failed to copy welcome email to support inbox: {e}")

    return sent


# ── Login failure alert ───────────────────────────────────────────────────────
# Deliberately does NOT fire on an ordinary wrong password — users mistype
# constantly and that would bury the inbox.  It fires when logins are actually
# broken (the endpoint raised) or when one account fails repeatedly enough that
# the person is plainly stuck.
_LOGIN_ALERT_LAST_SENT: dict[str, float] = {}
_LOGIN_ALERT_COOLDOWN_SEC = 900          # at most one alert per key per 15 min


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def send_login_failure_alert(
    email: Optional[str],
    detail: str,
) -> bool:
    """
    Tell the support inbox that the site could not sign someone in.

    Only for site faults — a wrong email or password never reaches here, since
    that is the user's own credential problem and alerting on it would bury the
    inbox in noise from ordinary typos.
    """
    import time

    key = email or "-"
    now = time.time()
    if now - _LOGIN_ALERT_LAST_SENT.get(key, 0.0) < _LOGIN_ALERT_COOLDOWN_SEC:
        log.debug(f"Login alert suppressed (cooldown): {key}")
        return False
    _LOGIN_ALERT_LAST_SENT[key] = now

    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto;padding:24px">
      <span style="background:#b91c1c;color:#fff;font-size:11px;font-weight:700;
                   padding:3px 9px;border-radius:99px">LOGIN FAILURE</span>
      <h2 style="margin:12px 0 4px;color:#111827">Sign-in is failing</h2>
      <p style="color:#374151;font-size:14px">
        A login attempt failed with a server error, not bad credentials. This
        usually means the database or another dependency is unavailable, so
        <strong>users cannot sign in</strong>.
      </p>
      <table style="width:100%;border-collapse:collapse;margin:18px 0;font-size:14px">
        <tr><td style="padding:5px 0;color:#6b7280;width:110px">Account</td>
            <td style="padding:5px 0;color:#111827">{html_escape(email or 'unknown')}</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">Error</td>
            <td style="padding:5px 0;color:#111827">{html_escape(detail)}</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">Detected</td>
            <td style="padding:5px 0;color:#111827">{_utcnow()}</td></tr>
      </table>
      <p style="font-size:13px;color:#6b7280">Check the server:</p>
      <pre style="background:#111827;color:#e5e7eb;padding:12px;border-radius:8px;
                  font-size:12px;overflow-x:auto">systemctl status asx-backend postgresql@16-main
journalctl -u asx-backend -n 100 --no-pager</pre>
      <p style="font-size:12px;color:#9ca3af">
        Further alerts for this account are suppressed for 15 minutes.
      </p>
    </div>
    """

    resend = _client()
    if resend is None:
        log.info(f"[email no-op] Login failure alert for {email}")
        return False
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [settings.SUPPORT_EMAIL],
            "subject": "[ASX Screener] Sign-in is failing",
            "html":    html,
        })
        log.info(f"Login failure alert sent for {email}")
        return True
    except Exception as e:
        log.error(f"Failed to send login failure alert: {e}")
        return False


# ── Founding member offer reminder (marketing) ────────────────────────────────
# Commercial message under the Spam Act 2003 (Cth): every send must identify the
# sender and carry a working unsubscribe link, and only users with
# marketing_emails_enabled = TRUE may receive it.
def send_founding_offer_email(
    to_email: str,
    name: Optional[str],
    unsubscribe_url: str,
    deadline: str = "30 September 2026",
) -> bool:
    """Remind a free user that the founding member offer is closing."""
    resend = _client()
    greeting = f"Hi {html_escape(name)}," if name else "Hi,"

    html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:auto;padding:24px">
      <p style="margin:0 0 6px;font-size:12px;letter-spacing:.08em;
                text-transform:uppercase;color:#b45309;font-weight:700">
        Founding member offer
      </p>
      <h2 style="margin:0 0 14px;color:#111827;font-size:22px;line-height:1.25">
        Closing {html_escape(deadline)}
      </h2>

      <p style="color:#374151;font-size:15px;margin:0 0 8px">{greeting}</p>
      <p style="color:#374151;font-size:15px;margin:0 0 18px">
        You've been using the free version of ASX Screener. Before the founding
        member offer closes, it's worth knowing what it gives you &mdash; because
        it won't be repeated.
      </p>

      <div style="border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin:0 0 20px">
        <div style="padding:16px 18px;border-bottom:1px solid #e5e7eb">
          <p style="margin:0 0 3px;font-size:15px;color:#111827">
            <strong>Pay for 1 year</strong> &rarr; get <strong>3 years</strong> of access
          </p>
          <p style="margin:0;font-size:13px;color:#6b7280">
            Our best value &mdash; two extra years at no additional charge.
          </p>
        </div>
        <div style="padding:16px 18px">
          <p style="margin:0 0 3px;font-size:15px;color:#111827">
            <strong>Pay for 1 month</strong> &rarr; get <strong>6 months</strong> of access
          </p>
          <p style="margin:0;font-size:13px;color:#6b7280">
            Prefer to start small? Five extra months, same idea.
          </p>
        </div>
      </div>

      <p style="color:#374151;font-size:14px;margin:0 0 8px">What that unlocks:</p>
      <ul style="margin:0 0 22px;padding-left:18px;font-size:14px">
        <li style="margin:5px 0;color:#374151">The full screener &mdash; 300+ metrics, no result caps</li>
        <li style="margin:5px 0;color:#374151">Alpha Screens, including AlphaFive, our weekly ranked top 5 from the ASX 200</li>
        <li style="margin:5px 0;color:#374151">AI Query &mdash; ask for a screen in plain English</li>
        <li style="margin:5px 0;color:#374151">Unlimited saved screens, watchlists and price alerts</li>
        <li style="margin:5px 0;color:#374151">Franking, mining and A-REIT depth built for the ASX</li>
      </ul>

      <a href="https://asxscreener.com.au/pricing"
         style="display:inline-block;padding:12px 24px;background:#f59e0b;color:#111827;
                border-radius:8px;text-decoration:none;font-weight:700;font-size:15px">
        Claim my spot
      </a>

      <p style="margin-top:20px;font-size:13px;color:#6b7280">
        After {html_escape(deadline)} the founding member terms end and plans move to
        standard pricing. Existing founding members keep their access.
      </p>

      <hr style="margin-top:28px;border:none;border-top:1px solid #e5e7eb"/>
      <p style="font-size:11px;color:#9ca3af;line-height:1.6">
        ASX Screener &middot; Australian stock analysis &middot;
        <a href="https://asxscreener.com.au" style="color:#9ca3af">asxscreener.com.au</a><br/>
        Information and educational tools only &mdash; not financial advice or a
        recommendation to buy or sell any security. Always do your own research.<br/>
        You're receiving this because you have an ASX Screener account.
        <a href="{html_escape(unsubscribe_url)}" style="color:#6b7280;text-decoration:underline">
          Unsubscribe from offers</a> &mdash; takes one click, and won't affect your
        price alerts.
      </p>
    </div>
    """

    if resend is None:
        log.info(f"[email no-op] Founding offer reminder for {to_email}")
        return False
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [to_email],
            "subject": f"Your founding member offer closes {deadline}",
            "html":    html,
        })
        log.info(f"Founding offer reminder sent to {to_email}")
        return True
    except Exception as e:
        log.error(f"Failed to send founding offer reminder to {to_email}: {e}")
        return False
