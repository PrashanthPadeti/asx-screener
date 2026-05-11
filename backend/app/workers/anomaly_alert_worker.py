"""
Anomaly Alert Email Worker
===========================
Runs at 7:15pm AEST daily — 15 min after anomaly detection completes.

For each user who:
  - has a watchlist containing stocks with newly detected HIGH or MEDIUM anomalies
  - has email notifications enabled

Sends a single digest email per user listing all flagged watchlist stocks.

Dedup guard: skips stocks whose anomaly was already notified today
(checks users.notification_history for anomaly_alert type + same asx_code + today).
"""
import json
import logging
from datetime import date, timezone, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)

# Only alert on high/medium — low severity anomalies are noise
ALERT_SEVERITIES = ("high", "medium")


async def send_anomaly_alerts() -> None:
    """Main entry point called by APScheduler."""
    async with AsyncSessionLocal() as db:
        try:
            await _run(db)
        except Exception as e:
            log.error("Anomaly alert worker error: %s", e, exc_info=True)


async def _run(db: AsyncSession) -> None:
    # ── Get all active high/medium anomalies ─────────────────────────────────
    rows = (await db.execute(text("""
        SELECT a.asx_code, a.flag_type, a.description, a.severity, a.detected_at,
               COALESCE(u.company_name, a.asx_code) AS company_name,
               u.price, u.return_1w
        FROM market.anomalies a
        LEFT JOIN screener.universe u ON u.asx_code = a.asx_code
        WHERE a.is_active = TRUE
          AND a.severity = ANY(:sevs)
        ORDER BY
            CASE a.severity WHEN 'high' THEN 1 ELSE 2 END,
            a.detected_at DESC
    """), {"sevs": list(ALERT_SEVERITIES)})).mappings().all()

    if not rows:
        log.info("Anomaly alerts: no active high/medium anomalies — skipping")
        return

    # Index anomalies by asx_code
    anomaly_map: dict[str, list[dict]] = {}
    for r in rows:
        code = r["asx_code"]
        anomaly_map.setdefault(code, []).append(dict(r))

    flagged_codes = set(anomaly_map.keys())
    log.info("Anomaly alerts: %d stocks with active anomalies", len(flagged_codes))

    # ── Find users with watchlist stocks in the flagged set ───────────────────
    users = (await db.execute(text("""
        SELECT DISTINCT
               usr.id         AS user_id,
               usr.email,
               usr.name,
               COALESCE(np.email_enabled, TRUE) AS email_enabled
        FROM users.users usr
        JOIN users.watchlists wl  ON wl.user_id = usr.id
        JOIN users.watchlist_items wi ON wi.watchlist_id = wl.id
        LEFT JOIN users.notification_preferences np ON np.user_id = usr.id
        WHERE usr.email IS NOT NULL
          AND COALESCE(np.email_enabled, TRUE) = TRUE
          AND wi.asx_code = ANY(:codes)
    """), {"codes": list(flagged_codes)})).mappings().all()

    if not users:
        log.info("Anomaly alerts: no eligible users watching affected stocks")
        return

    log.info("Anomaly alerts: %d users to notify", len(users))
    sent = 0

    for user in users:
        user_id = str(user["user_id"])
        try:
            await _notify_user(db, user_id, user["email"], user["name"], anomaly_map)
            sent += 1
        except Exception as e:
            log.error("Anomaly alert failed for user %s: %s", user_id, e)

    await db.commit()
    log.info("Anomaly alerts complete — %d/%d users notified", sent, len(users))


async def _notify_user(
    db: AsyncSession,
    user_id: str,
    email: str,
    name: Optional[str],
    anomaly_map: dict[str, list[dict]],
) -> None:
    # Get this user's watchlist stocks that have anomalies
    wl_rows = (await db.execute(text("""
        SELECT DISTINCT wi.asx_code
        FROM users.watchlists wl
        JOIN users.watchlist_items wi ON wi.watchlist_id = wl.id
        WHERE wl.user_id = :uid
    """), {"uid": user_id})).scalars().all()

    watched = set(wl_rows)
    affected = {code: flags for code, flags in anomaly_map.items() if code in watched}

    if not affected:
        return

    # ── Dedup: skip stocks already alerted today ──────────────────────────────
    today_str = date.today().isoformat()
    already_alerted = set((await db.execute(text("""
        SELECT metadata->>'asx_code'
        FROM users.notification_history
        WHERE user_id = CAST(:uid AS uuid)
          AND notification_type = 'anomaly_alert'
          AND DATE(created_at) = :today
    """), {"uid": user_id, "today": today_str})).scalars().all())

    new_affected = {code: flags for code, flags in affected.items()
                    if code not in already_alerted}

    if not new_affected:
        log.debug("Anomaly alert: user %s already notified for all affected stocks today", user_id)
        return

    # ── Build and send email ──────────────────────────────────────────────────
    subject = _build_subject(new_affected)
    html    = _build_html(name, new_affected)

    from app.services.notification_service import _send_raw_email
    ok = _send_raw_email(email, subject, html)
    status = "sent" if ok else "failed"

    # Log one history entry per affected stock
    for code in new_affected:
        meta = {
            "asx_code":      code,
            "anomaly_count": len(new_affected[code]),
            "severities":    list({f["severity"] for f in new_affected[code]}),
        }
        await db.execute(text("""
            INSERT INTO users.notification_history
                (user_id, channel, notification_type, subject, recipient,
                 status, metadata, attempt_count, sent_at)
            VALUES
                (CAST(:uid AS uuid), 'email', 'anomaly_alert', :subject, :email,
                 :status, :meta::jsonb, 1,
                 CASE WHEN :status = 'sent' THEN NOW() ELSE NULL END)
        """), {
            "uid":    user_id,
            "subject": subject,
            "email":  email,
            "status": status,
            "meta":   json.dumps(meta),
        })

    log.info("Anomaly alert email %s to %s for stocks: %s",
             status, email, ", ".join(sorted(new_affected)))


# ── Email content ─────────────────────────────────────────────────────────────

_SEV_COLORS = {"high": "#dc2626", "medium": "#d97706"}
_SEV_ICONS  = {"high": "🔴", "medium": "🟡"}

_FLAG_LABELS = {
    "volume_spike":      "Volume Spike",
    "price_gap_up":      "Price Gap Up",
    "price_gap_down":    "Price Gap Down",
    "rsi_overbought":    "RSI Overbought",
    "rsi_oversold":      "RSI Oversold",
    "high_short_int":    "High Short Interest",
    "new_52w_high":      "52-Week High",
    "new_52w_low":       "52-Week Low",
    "unusual_volume":    "Unusual Volume",
    "momentum_breakout": "Momentum Breakout",
}


def _build_subject(affected: dict[str, list[dict]]) -> str:
    high_count = sum(1 for flags in affected.values()
                     if any(f["severity"] == "high" for f in flags))
    codes = sorted(affected.keys())[:3]
    suffix = f" +{len(affected) - 3} more" if len(affected) > 3 else ""
    prefix = "🔴 " if high_count else "🟡 "
    return f"{prefix}ASX Anomaly Alert: {', '.join(codes)}{suffix}"


def _build_html(name: Optional[str], affected: dict[str, list[dict]]) -> str:
    greeting = f"Hi {name}," if name else "Hi,"

    rows_html = ""
    # Sort: high severity first, then by code
    sorted_items = sorted(
        affected.items(),
        key=lambda x: (0 if any(f["severity"] == "high" for f in x[1]) else 1, x[0])
    )

    for code, flags in sorted_items:
        top_flag    = flags[0]
        sev         = top_flag["severity"]
        sev_color   = _SEV_COLORS.get(sev, "#6b7280")
        sev_icon    = _SEV_ICONS.get(sev, "⚪")
        company_name = top_flag.get("company_name", code)
        price        = top_flag.get("price")
        ret_1w       = top_flag.get("return_1w")

        price_str = f"${float(price):.3f}" if price is not None else "—"
        ret_str   = (f"{float(ret_1w)*100:+.1f}% (1W)" if ret_1w is not None else "")

        flag_items = "".join(
            f"<li style='margin:2px 0;font-size:12px;color:#374151'>"
            f"{_FLAG_LABELS.get(f['flag_type'], f['flag_type'])}: {f['description']}"
            f"</li>"
            for f in flags[:3]
        )

        rows_html += f"""
        <div style="border:1px solid #e5e7eb;border-left:4px solid {sev_color};
                    border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <span style="font-weight:700;font-size:15px">{sev_icon} {code}</span>
              <span style="color:#6b7280;font-size:13px;margin-left:8px">{company_name}</span>
            </div>
            <div style="text-align:right;font-size:13px">
              <span style="font-weight:600">{price_str}</span>
              {"<span style='color:" + ("#16a34a" if ret_1w and float(ret_1w) > 0 else "#dc2626") + ";margin-left:6px'>" + ret_str + "</span>" if ret_str else ""}
            </div>
          </div>
          <ul style="list-style:none;padding:0;margin:8px 0 0">{flag_items}</ul>
          <a href="https://asxscreener.com.au/company/{code}"
             style="display:inline-block;margin-top:8px;font-size:12px;color:#2563eb">
            View {code} →
          </a>
        </div>"""

    body = f"""
    <p style="color:#374151;margin:0 0 16px">{greeting} Anomaly signals detected for stocks in your watchlist.</p>
    {rows_html}
    <p style="font-size:12px;color:#9ca3af;margin-top:16px">
      Anomalies are detected daily after market close. High severity signals warrant closer attention.
    </p>
    <a href="https://asxscreener.com.au/market"
       style="display:inline-block;margin-top:8px;padding:10px 20px;
              background:#2563eb;color:white;border-radius:8px;text-decoration:none;font-size:14px">
      View Market Anomalies
    </a>
    """

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
      <a href="https://asxscreener.com.au/notifications" style="color:#6b7280">Manage preferences</a> &middot;
      <a href="https://asxscreener.com.au/auth/unsubscribe" style="color:#6b7280">Unsubscribe</a>
    </p>
  </div>
</div>"""

    return _BASE.format(body=body)
