"""
ASX Screener — Watchlist Daily Digest Worker
=============================================
Sends a bundled daily email of watchlist stock movements to every user
who has at least one watchlist and has email notifications enabled.
Runs once per day at 7:30am AEST via APScheduler (registered in main.py).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.services.notification_service import _send_raw_email, _log_notification, _BASE, _GREEN, _RED

log = logging.getLogger(__name__)


async def send_watchlist_digests() -> None:
    """Main entry point called by APScheduler."""
    async with AsyncSessionLocal() as db:
        try:
            await _run_digests(db)
        except Exception as e:
            log.error(f"Watchlist digest error: {e}", exc_info=True)


async def _run_digests(db: AsyncSession) -> None:
    result = await db.execute(text("""
        SELECT DISTINCT u.id AS user_id, u.email, u.name,
               COALESCE(np.email_enabled, TRUE) AS email_enabled
        FROM users.users u
        JOIN users.watchlists wl ON wl.user_id = u.id
        LEFT JOIN users.notification_preferences np ON np.user_id = u.id
        WHERE u.email IS NOT NULL
          AND COALESCE(np.email_enabled, TRUE) = TRUE
    """))
    users = result.fetchall()

    if not users:
        log.info("Watchlist digest: no eligible users")
        return

    log.info(f"Sending watchlist digests to {len(users)} users")
    sent = 0
    for user in users:
        try:
            await _send_user_digest(db, str(user.user_id), user.email, user.name)
            sent += 1
        except Exception as e:
            log.error(f"Digest failed for user {user.user_id}: {e}")

    await db.commit()
    log.info(f"Watchlist digest complete — {sent}/{len(users)} sent")


async def _send_user_digest(db: AsyncSession, user_id: str, email: str, name: str | None) -> None:
    wl_rows = (await db.execute(text("""
        SELECT wl.id, wl.name, wi.asx_code
        FROM users.watchlists wl
        JOIN users.watchlist_items wi ON wi.watchlist_id = wl.id
        WHERE wl.user_id = :uid
        ORDER BY wl.created_at ASC, wi.sort_order ASC, wi.added_at ASC
    """), {"uid": user_id})).fetchall()

    if not wl_rows:
        return

    watchlists: dict[str, dict] = {}
    codes_set: set[str] = set()
    for r in wl_rows:
        wl_id = str(r.id)
        if wl_id not in watchlists:
            watchlists[wl_id] = {"name": r.name, "codes": []}
        watchlists[wl_id]["codes"].append(r.asx_code)
        codes_set.add(r.asx_code)

    if not codes_set:
        return

    codes = list(codes_set)
    placeholders = ', '.join(f':c{i}' for i in range(len(codes)))
    code_params  = {f'c{i}': c for i, c in enumerate(codes)}

    price_rows = (await db.execute(text(f"""
        SELECT u.asx_code, u.price, u.return_1d, u.return_1w, u.volume,
               c.company_name,
               anom.flag_type, anom.description AS anomaly_desc
        FROM screener.universe u
        LEFT JOIN market.companies c ON c.asx_code = u.asx_code
        LEFT JOIN LATERAL (
            SELECT flag_type, description
            FROM market.anomalies
            WHERE asx_code = u.asx_code AND is_active = TRUE
            ORDER BY detected_at DESC LIMIT 1
        ) anom ON TRUE
        WHERE u.asx_code IN ({placeholders})
    """), code_params)).fetchall()
    prices = {r.asx_code: r for r in price_rows}

    html = _build_digest_html(name, watchlists, prices)
    if not html:
        return

    today_str = datetime.now(timezone.utc).strftime('%d %b %Y')
    subject   = f"ASX Watchlist Digest — {today_str}"

    ok     = _send_raw_email(email, subject, html)
    status = "sent" if ok else "failed"
    meta   = {"watchlist_count": len(watchlists), "stock_count": len(codes)}
    await _log_notification(
        db, user_id, "email", "watchlist_digest", email,
        subject, status, meta,
        error_message=None if ok else "send failed",
    )


def _build_digest_html(name: str | None, watchlists: dict, prices: dict) -> str:
    greeting = f"Hi {name}," if name else "Hi,"
    sections = ""

    for wl in watchlists.values():
        rows_html = ""
        for code in wl["codes"]:
            p = prices.get(code)
            if not p:
                continue

            price   = float(p.price) if p.price else 0
            ret1d   = float(p.return_1d) if p.return_1d is not None else None
            company = (p.company_name or code)[:35]
            anomaly = p.anomaly_desc or (
                p.flag_type.replace("_", " ").title() if p.flag_type else None
            )

            ret_color = _GREEN if (ret1d or 0) >= 0 else _RED
            ret_str   = f"{ret1d:+.2f}%" if ret1d is not None else "—"
            anom_cell = (
                f'<br><span style="font-size:11px;color:#d97706;background:#fef3c7;'
                f'padding:1px 6px;border-radius:4px">{anomaly}</span>'
            ) if anomaly else ""

            rows_html += f"""
            <tr style="border-bottom:1px solid #f3f4f6">
              <td style="padding:7px 0">
                <strong style="font-size:13px">{code}</strong>
                <span style="color:#6b7280;font-size:12px;margin-left:6px">{company}</span>
                {anom_cell}
              </td>
              <td style="text-align:right;padding:7px 0;font-size:13px">${price:.3f}</td>
              <td style="text-align:right;padding:7px 0;font-size:13px;color:{ret_color}">{ret_str}</td>
            </tr>"""

        if not rows_html:
            continue

        sections += f"""
        <div style="margin-bottom:24px">
          <h3 style="font-size:14px;color:#374151;margin:0 0 8px;
                     border-bottom:2px solid #e5e7eb;padding-bottom:6px">{wl['name']}</h3>
          <table style="width:100%;border-collapse:collapse;font-size:13px">
            <thead>
              <tr style="border-bottom:1px solid #e5e7eb">
                <th style="text-align:left;padding:5px 0;color:#6b7280;font-weight:500">Stock</th>
                <th style="text-align:right;padding:5px 0;color:#6b7280;font-weight:500">Price</th>
                <th style="text-align:right;padding:5px 0;color:#6b7280;font-weight:500">1D Chg</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>"""

    if not sections:
        return ""

    body = f"""
    <p style="color:#374151;margin:0 0 16px">{greeting} Here's your daily ASX watchlist update.</p>
    {sections}
    <a href="http://asxscreener.com.au/watchlist"
       style="display:inline-block;margin-top:8px;padding:10px 20px;background:#2563eb;
              color:white;border-radius:8px;text-decoration:none;font-size:14px">
      Open Watchlists →
    </a>
    """
    return _BASE.format(body=body)
