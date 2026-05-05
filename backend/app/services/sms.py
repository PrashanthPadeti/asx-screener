"""
ASX Screener — SMS Service (Twilio)
Falls back to no-op log if TWILIO_* env vars are not set.
"""
import logging
from app.core.config import settings

log = logging.getLogger(__name__)


def _client():
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return None
    from twilio.rest import Client
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def send_sms(to_number: str, body: str) -> bool:
    """Send an SMS. Returns True on success."""
    client = _client()
    if client is None:
        log.info(f"[sms no-op] To: {to_number} | {body[:80]}")
        return False

    if not to_number.startswith("+"):
        to_number = "+61" + to_number.lstrip("0")

    try:
        msg = client.messages.create(
            body=body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to_number,
        )
        log.info(f"SMS sent to {to_number}: sid={msg.sid}")
        return True
    except Exception as e:
        log.error(f"SMS send failed to {to_number}: {e}")
        return False
