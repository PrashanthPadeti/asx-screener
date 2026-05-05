"""
ASX Screener — Unified Notification Service
============================================
Single entry point for all outbound notifications (email + SMS).
Writes to users.notification_history for every attempt.
Handles retry logic: up to 3 attempts with exponential backoff.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email import send_alert_email, send_welcome_email
from app.services.sms import send_sms

log = logging.getLogger(__name__)

MAX_RETRIES = 3


# ── History helpers ───────────────────────────────────────────────────────────

async def _log_notification(
    db: AsyncSession,
    user_id: str,
    channel: str,
    notification_type: str,
    recipient: str,
    subject: Optional[str],
    status: str,
    metadata: dict,
    error_message: Optional[str] = None,
    attempt_count: int = 1,
) -> None:
    await db.execute(text("""
        INSERT INTO users.notification_history
            (user_id, channel, notification_type, subject, recipient,
             status, error_message, metadata, attempt_count, sent_at)
        VALUES
            (:uid, :channel, :type, :subject, :recipient,
             :status, :error, :meta::jsonb, :attempts,
             CASE WHEN :status = 'sent' THEN NOW() ELSE NULL END)
    """), {
        "uid":      user_id,
        "channel":  channel,
        "type":     notification_type,
        "subject":  subject,
        "recipient": recipient,
        "status":   status,
        "error":    error_message,
        "meta":     __import__("json").dumps(metadata),
        "attempts": attempt_count,
    })


# ── Alert notification ────────────────────────────────────────────────────────

async def send_alert_notification(
    db: AsyncSession,
    user_id: str,
    email: Optional[str],
    phone: Optional[str],
    asx_code: str,
    alert_type: str,
    threshold: float,
    current_value: float,
    company_name: Optional[str],
    via_email: bool,
    via_sms: bool,
) -> None:
    label = company_name or asx_code
    direction = "rose above" if "above" in alert_type else "fell below"

    if "pct_change" in alert_type:
        sms_body = f"ASX Alert: {asx_code} moved {current_value:+.2f}% (threshold: {threshold:+.2f}%). asxscreener.com.au"
    else:
        sms_body = f"ASX Alert: {asx_code} {direction} ${threshold:.3f} (now ${current_value:.3f}). asxscreener.com.au"

    meta = {"asx_code": asx_code, "alert_type": alert_type, "threshold": threshold, "current_value": current_value}

    if via_email and email:
        for attempt in range(1, MAX_RETRIES + 1):
            ok = send_alert_email(
                to_email=email,
                asx_code=asx_code,
                alert_type=alert_type,
                threshold=threshold,
                current_value=current_value,
                company_name=company_name,
            )
            if ok:
                await _log_notification(db, user_id, "email", "price_alert", email,
                                        f"ASX Alert: {asx_code}", "sent", meta, attempt_count=attempt)
                break
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
        else:
            await _log_notification(db, user_id, "email", "price_alert", email,
                                    f"ASX Alert: {asx_code}", "failed", meta,
                                    error_message="Max retries exceeded", attempt_count=MAX_RETRIES)

    if via_sms and phone:
        for attempt in range(1, MAX_RETRIES + 1):
            ok = send_sms(phone, sms_body)
            if ok:
                await _log_notification(db, user_id, "sms", "price_alert", phone,
                                        None, "sent", meta, attempt_count=attempt)
                break
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
        else:
            await _log_notification(db, user_id, "sms", "price_alert", phone,
                                    None, "failed", meta,
                                    error_message="Max retries exceeded", attempt_count=MAX_RETRIES)


# ── Portfolio threshold notification ─────────────────────────────────────────

async def send_portfolio_threshold_notification(
    db: AsyncSession,
    user_id: str,
    email: Optional[str],
    phone: Optional[str],
    portfolio_name: str,
    current_value: float,
    previous_value: float,
    change_pct: float,
    via_email: bool,
    via_sms: bool,
) -> None:
    direction = "gained" if change_pct >= 0 else "lost"
    subject   = f"Portfolio Alert: {portfolio_name} {direction} {abs(change_pct):.1f}%"
    sms_body  = (
        f"Portfolio '{portfolio_name}' {direction} {abs(change_pct):.1f}% "
        f"(${previous_value:,.0f} → ${current_value:,.0f}). asxscreener.com.au/portfolio"
    )
    meta = {
        "portfolio_name": portfolio_name,
        "current_value":  current_value,
        "previous_value": previous_value,
        "change_pct":     change_pct,
    }

    if via_email and email:
        html = _portfolio_threshold_html(portfolio_name, current_value, previous_value, change_pct)
        ok = _send_raw_email(email, subject, html)
        status = "sent" if ok else "failed"
        await _log_notification(db, user_id, "email", "portfolio_threshold",
                                email, subject, status, meta,
                                error_message=None if ok else "send failed")

    if via_sms and phone:
        ok = send_sms(phone, sms_body)
        status = "sent" if ok else "failed"
        await _log_notification(db, user_id, "sms", "portfolio_threshold",
                                phone, None, status, meta,
                                error_message=None if ok else "send failed")


# ── Weekly portfolio summary ──────────────────────────────────────────────────

async def send_weekly_portfolio_email(
    db: AsyncSession,
    user_id: str,
    email: str,
    name: Optional[str],
    portfolios: list[dict],
) -> None:
    if not portfolios:
        return

    subject = "Your Weekly ASX Portfolio Summary"
    html    = _weekly_summary_html(name, portfolios)
    meta    = {"portfolio_count": len(portfolios)}

    ok = _send_raw_email(email, subject, html)
    status = "sent" if ok else "failed"
    await _log_notification(db, user_id, "email", "portfolio_weekly",
                            email, subject, status, meta,
                            error_message=None if ok else "send failed")


# ── Announcement notification ─────────────────────────────────────────────────

async def send_announcement_notification(
    db: AsyncSession,
    user_id: str,
    email: Optional[str],
    phone: Optional[str],
    asx_code: str,
    company_name: Optional[str],
    title: str,
    doc_type: str,
    url: Optional[str],
    via_email: bool,
    via_sms: bool,
) -> None:
    label   = company_name or asx_code
    subject = f"ASX Announcement: {asx_code} — {doc_type}"
    sms_body = f"ASX: {asx_code} ({label}) filed '{doc_type}'. asxscreener.com.au/company/{asx_code}"
    meta     = {"asx_code": asx_code, "doc_type": doc_type, "title": title}

    if via_email and email:
        html = _announcement_html(asx_code, label, title, doc_type, url)
        ok = _send_raw_email(email, subject, html)
        status = "sent" if ok else "failed"
        await _log_notification(db, user_id, "email", "announcement",
                                email, subject, status, meta,
                                error_message=None if ok else "send failed")

    if via_sms and phone:
        ok = send_sms(phone, sms_body)
        status = "sent" if ok else "failed"
        await _log_notification(db, user_id, "sms", "announcement",
                                phone, None, status, meta,
                                error_message=None if ok else "send failed")


# ── Low-level email sender ────────────────────────────────────────────────────

def _send_raw_email(to_email: str, subject: str, html: str) -> bool:
    from app.core.config import settings
    if not settings.RESEND_API_KEY:
        log.info(f"[email no-op] {subject} → {to_email}")
        return False
    import resend
    resend.api_key = settings.RESEND_API_KEY
    try:
        resend.Emails.send({
            "from":    settings.EMAIL_FROM,
            "to":      [to_email],
            "subject": subject,
            "html":    html,
        })
        return True
    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False


# ── HTML templates ─────────────────────────────────────────────────────────────

_BASE = """
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            max-width:560px;margin:auto;background:#fff;border-radius:12px;
            border:1px solid #e5e7eb;overflow:hidden">
  <div style="background:#1e3a5f;padding:20px 24px">
    <h1 style="color:#fff;margin:0;font-size:18px">🇦🇺 ASX Screener</h1>
  </div>
  <div style="padding:24px">{body}</div>
  <div style="background:#f9fafb;padding:16px 24px;border-top:1px solid #e5e7eb">
    <p style="font-size:11px;color:#9ca3af;margin:0">
      ASX Screener &middot;
      <a href="http://asxscreener.com.au/notifications" style="color:#6b7280">Manage preferences</a> &middot;
      <a href="http://asxscreener.com.au/auth/unsubscribe" style="color:#6b7280">Unsubscribe</a>
    </p>
  </div>
</div>
"""

_GREEN = "#16a34a"
_RED   = "#dc2626"


def _portfolio_threshold_html(name: str, current: float, previous: float, pct: float) -> str:
    color = _GREEN if pct >= 0 else _RED
    arrow = "↑" if pct >= 0 else "↓"
    body  = f"""
    <h2 style="color:#111827;margin:0 0 8px">Portfolio Alert</h2>
    <p style="font-size:16px;font-weight:600;color:{color};margin:0 0 16px">
      {arrow} {name} moved {pct:+.1f}%
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      <tr><td style="color:#6b7280;padding:4px 0">Previous value</td>
          <td style="text-align:right;font-weight:600">${previous:,.2f}</td></tr>
      <tr><td style="color:#6b7280;padding:4px 0">Current value</td>
          <td style="text-align:right;font-weight:600;color:{color}">${current:,.2f}</td></tr>
      <tr><td style="color:#6b7280;padding:4px 0">Change</td>
          <td style="text-align:right;font-weight:600;color:{color}">{pct:+.2f}%</td></tr>
    </table>
    <a href="http://asxscreener.com.au/portfolio"
       style="display:inline-block;margin-top:20px;padding:10px 20px;
              background:#2563eb;color:white;border-radius:8px;text-decoration:none;font-size:14px">
      View Portfolio
    </a>
    """
    return _BASE.format(body=body)


def _weekly_summary_html(name: Optional[str], portfolios: list[dict]) -> str:
    greeting = f"Hi {name}," if name else "Hi,"
    rows = ""
    total_value = sum(p.get("total_value", 0) for p in portfolios)
    total_gain  = sum(p.get("total_gain_loss", 0) for p in portfolios)

    for p in portfolios:
        v    = p.get("total_value", 0)
        gl   = p.get("total_gain_loss", 0)
        pct  = p.get("total_return_pct", 0)
        col  = _GREEN if gl >= 0 else _RED
        rows += f"""
        <tr style="border-bottom:1px solid #f3f4f6">
          <td style="padding:8px 0;font-weight:600">{p.get("name","Portfolio")}</td>
          <td style="text-align:right;padding:8px 0">${v:,.2f}</td>
          <td style="text-align:right;padding:8px 0;color:{col}">{gl:+,.2f}</td>
          <td style="text-align:right;padding:8px 0;color:{col}">{pct:+.2f}%</td>
        </tr>"""

    gainers = ""
    for p in portfolios:
        for h in sorted(p.get("holdings", []), key=lambda x: x.get("gain_pct", 0), reverse=True)[:3]:
            gainers += f"<li style='margin:4px 0'><strong>{h['asx_code']}</strong> {h.get('gain_pct', 0):+.1f}%</li>"

    losers = ""
    for p in portfolios:
        for h in sorted(p.get("holdings", []), key=lambda x: x.get("gain_pct", 0))[:3]:
            losers += f"<li style='margin:4px 0'><strong>{h['asx_code']}</strong> {h.get('gain_pct', 0):+.1f}%</li>"

    total_col = _GREEN if total_gain >= 0 else _RED
    body = f"""
    <p style="color:#374151;margin:0 0 16px">{greeting} Here's your weekly portfolio summary.</p>

    <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:20px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <p style="font-size:12px;color:#6b7280;margin:0">Total Portfolio Value</p>
          <p style="font-size:24px;font-weight:700;color:#111827;margin:4px 0">${total_value:,.2f}</p>
        </div>
        <div style="text-align:right">
          <p style="font-size:12px;color:#6b7280;margin:0">Total P&L</p>
          <p style="font-size:18px;font-weight:600;color:{total_col};margin:4px 0">{total_gain:+,.2f}</p>
        </div>
      </div>
    </div>

    <h3 style="font-size:14px;color:#374151;margin:0 0 8px">Portfolio Breakdown</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
      <thead>
        <tr style="border-bottom:2px solid #e5e7eb">
          <th style="text-align:left;padding:6px 0;color:#6b7280;font-weight:500">Portfolio</th>
          <th style="text-align:right;padding:6px 0;color:#6b7280;font-weight:500">Value</th>
          <th style="text-align:right;padding:6px 0;color:#6b7280;font-weight:500">P&L</th>
          <th style="text-align:right;padding:6px 0;color:#6b7280;font-weight:500">Return</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    {"<h3 style='font-size:14px;color:#374151;margin:0 0 8px'>Top Gainers</h3><ul style='list-style:none;padding:0;margin:0 0 16px;font-size:13px'>" + gainers + "</ul>" if gainers else ""}
    {"<h3 style='font-size:14px;color:#374151;margin:0 0 8px'>Top Losers</h3><ul style='list-style:none;padding:0;margin:0 0 16px;font-size:13px'>" + losers + "</ul>" if losers else ""}

    <a href="http://asxscreener.com.au/portfolio"
       style="display:inline-block;margin-top:8px;padding:10px 20px;
              background:#2563eb;color:white;border-radius:8px;text-decoration:none;font-size:14px">
      Open Portfolio
    </a>
    """
    return _BASE.format(body=body)


def _announcement_html(code: str, label: str, title: str, doc_type: str, url: Optional[str]) -> str:
    link = f'<a href="{url}" style="color:#2563eb">View document ↗</a>' if url else ""
    body = f"""
    <h2 style="color:#111827;margin:0 0 4px">ASX Announcement</h2>
    <p style="font-size:12px;color:#6b7280;margin:0 0 16px">Market-sensitive filing</p>
    <div style="background:#eff6ff;border-left:4px solid #2563eb;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px">
      <p style="font-weight:700;font-size:16px;margin:0">{code} — {label}</p>
      <p style="color:#374151;margin:4px 0 0;font-size:14px">{title}</p>
    </div>
    <table style="font-size:13px;width:100%">
      <tr><td style="color:#6b7280;padding:3px 0">Type</td><td style="font-weight:500">{doc_type}</td></tr>
    </table>
    <div style="margin-top:16px">{link}</div>
    <a href="http://asxscreener.com.au/company/{code}"
       style="display:inline-block;margin-top:12px;padding:10px 20px;
              background:#2563eb;color:white;border-radius:8px;text-decoration:none;font-size:14px">
      View {code}
    </a>
    """
    return _BASE.format(body=body)
