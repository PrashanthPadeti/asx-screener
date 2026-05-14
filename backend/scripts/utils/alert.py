"""
Pipeline Failure Alerting — ASX Screener
=========================================
Sends an email via Resend when a data pipeline step fails.

Usage (from any pipeline script):

    from scripts.utils.alert import send_failure_alert

    # In run() before sys.exit():
    send_failure_alert(
        pipeline="daily",
        step="Step 4: Daily compute engine",
        target_date="2026-05-14",
        exit_code=1,
    )

Environment variables (read from .env in repo root or process env):
    RESEND_API_KEY   — Resend API key
    EMAIL_FROM       — sender address (default: noreply@asxscreener.com.au)
    ADMIN_EMAILS     — comma-separated recipient list
"""

import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ── Load .env if running as a standalone script (not via FastAPI) ─────────────
def _load_env() -> None:
    """Best-effort .env load — silently skips if dotenv not installed."""
    try:
        from dotenv import load_dotenv
        # Walk up from this file to find the backend .env
        for parent in Path(__file__).parents:
            env_file = parent / ".env"
            if env_file.exists():
                load_dotenv(env_file, override=False)
                break
    except ImportError:
        pass


_load_env()


def send_failure_alert(
    pipeline: str,
    step: str,
    target_date: str,
    exit_code: int = 1,
) -> None:
    """
    Send a pipeline failure alert email via Resend.
    Silently swallows errors so a broken alert never masks the real failure.

    Args:
        pipeline:    Short name e.g. "daily", "weekly", "monthly"
        step:        The step label that failed e.g. "Step 4: Daily compute engine"
        target_date: ISO date string the pipeline was processing
        exit_code:   The subprocess exit code that triggered the failure
    """
    api_key    = os.getenv("RESEND_API_KEY", "")
    from_addr  = os.getenv("EMAIL_FROM", "noreply@asxscreener.com.au")
    admin_raw  = os.getenv("ADMIN_EMAILS", "asxscreener@gmail.com")
    recipients = [e.strip() for e in admin_raw.split(",") if e.strip()]

    if not api_key:
        log.warning("send_failure_alert: RESEND_API_KEY not set — skipping email alert")
        return
    if not recipients:
        log.warning("send_failure_alert: ADMIN_EMAILS not set — skipping email alert")
        return

    now_utc  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hostname = socket.gethostname()
    pipeline_cap = pipeline.capitalize()

    subject = f"⚠️ ASX Screener — {pipeline_cap} pipeline FAILED ({target_date})"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    body      {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                 background: #f5f5f5; margin: 0; padding: 20px; color: #333; }}
    .card     {{ background: #fff; border-radius: 8px; max-width: 600px; margin: 0 auto;
                 padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
    .badge    {{ display: inline-block; background: #ef4444; color: #fff;
                 padding: 4px 12px; border-radius: 999px; font-size: 12px;
                 font-weight: 700; letter-spacing: .5px; margin-bottom: 16px; }}
    h2        {{ margin: 0 0 24px; font-size: 20px; }}
    table     {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    td        {{ padding: 8px 12px; font-size: 14px; }}
    tr:nth-child(odd)  td {{ background: #f9fafb; }}
    .label    {{ color: #6b7280; width: 140px; }}
    .footer   {{ margin-top: 24px; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; padding-top: 16px; }}
    code      {{ background: #1e293b; color: #f8fafc; padding: 10px 14px; border-radius: 6px;
                 display: block; font-size: 13px; margin: 8px 0; white-space: pre; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">PIPELINE FAILURE</div>
    <h2>ASX Screener — {pipeline_cap} pipeline failed</h2>

    <table>
      <tr><td class="label">Pipeline</td><td><strong>{pipeline_cap}</strong></td></tr>
      <tr><td class="label">Failed step</td><td><strong>{step}</strong></td></tr>
      <tr><td class="label">Target date</td><td>{target_date}</td></tr>
      <tr><td class="label">Exit code</td><td>{exit_code}</td></tr>
      <tr><td class="label">Detected at</td><td>{now_utc}</td></tr>
      <tr><td class="label">Server</td><td>{hostname}</td></tr>
    </table>

    <p style="margin-top:20px;font-size:14px;">Check the logs on the server:</p>
    <code>pm2 logs asx-backend --lines 100
tail -100 /opt/asx-screener/logs/{pipeline}_pipeline.log</code>

    <p style="font-size:14px;">Or SSH in and re-run manually:</p>
    <code>cd /opt/asx-screener
asx-venv/bin/python scripts/eodhd/v2/jobs/{pipeline}_pipeline.py</code>

    <div class="footer">
      This alert was sent automatically by the ASX Screener pipeline monitor.<br>
      To stop these alerts, unset ADMIN_EMAILS in your .env file.
    </div>
  </div>
</body>
</html>
"""

    text_body = (
        f"ASX Screener — {pipeline_cap} pipeline FAILED\n\n"
        f"Pipeline:    {pipeline_cap}\n"
        f"Failed step: {step}\n"
        f"Target date: {target_date}\n"
        f"Exit code:   {exit_code}\n"
        f"Detected at: {now_utc}\n"
        f"Server:      {hostname}\n\n"
        f"Check logs:\n"
        f"  tail -100 /opt/asx-screener/logs/{pipeline}_pipeline.log\n"
    )

    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from":    from_addr,
            "to":      recipients,
            "subject": subject,
            "html":    html_body,
            "text":    text_body,
        })
        log.info(f"Failure alert sent to {recipients} for {pipeline} pipeline step: {step}")
    except Exception as exc:
        log.error(f"send_failure_alert: failed to send email — {exc}")
