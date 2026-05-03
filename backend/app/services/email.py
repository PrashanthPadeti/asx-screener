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
