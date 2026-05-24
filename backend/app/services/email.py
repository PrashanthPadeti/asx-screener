"""
ASX Screener — Email Service (Resend)
========================================
Thin wrapper around the Resend SDK.
Falls back to a no-op log if RESEND_API_KEY is not configured.
"""
import logging
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
    """Send a welcome email to a new user."""
    resend = _client()
    if resend is None:
        log.info(f"[email no-op] Welcome email for {to_email}")
        return False

    greeting = f"Hi {name}," if name else "Hi,"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
      <h2 style="color:#1d4ed8">Welcome to ASX Screener 🇦🇺</h2>
      <p>{greeting}</p>
      <p>Thanks for signing up. You can now:</p>
      <ul>
        <li>Screen all ~1,800 ASX companies with 80+ filters</li>
        <li>Save watchlists synced across devices</li>
        <li>Set price alerts with email notifications</li>
      </ul>
      <a href="http://asxscreener.com.au/screener"
         style="display:inline-block;margin-top:16px;padding:10px 20px;
                background:#2563eb;color:white;border-radius:8px;text-decoration:none">
        Start Screening
      </a>
    </div>
    """
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [to_email],
            "subject": "Welcome to ASX Screener",
            "html":    html,
        })
        return True
    except Exception as e:
        log.error(f"Failed to send welcome email: {e}")
        return False
