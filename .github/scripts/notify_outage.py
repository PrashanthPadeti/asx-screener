#!/usr/bin/env python3
"""
Tell a human the site is down.

The sentinel detected production unavailable on 3, 4 and 5 October 2026 and
nobody found out until someone tried to log in on the third morning. The
detector was never the problem. This is the part that was missing.

    detection   uptime_probe.py        -- worked, three times out of three
    delivery    this                   -- did not exist

Sends through Resend, which the product already uses, over HTTPS from GitHub's
runners. Nothing here touches the production host: a notifier that needed the
thing it reports on would be silent exactly when it matters.

Failure semantics, deliberately loud
------------------------------------
A missing or malformed credential EXITS NON-ZERO. It does not warn and carry
on. A notifier that degrades quietly is worse than none, because the silence
afterwards reads as "no outage" rather than "no notifier" -- which is precisely
the confusion that cost three days here.

Delivery is reported as the API's own verdict: the HTTP status and the message
id it returns. "The step ran" is not evidence that a message was sent.

Environment:
    RESEND_API_KEY     required
    ALERT_EMAIL_TO     required, comma-separated
    ALERT_EMAIL_FROM   required, a sender on a domain verified in Resend

Usage:
    python3 notify_outage.py --subject "..." --body "..."
    python3 notify_outage.py --self-test        # no network, no credentials
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

RESEND_ENDPOINT = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 20


class Misconfigured(SystemExit):
    """Raised loudly. A notifier that cannot send must not look like silence."""


def _required(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise Misconfigured(
            f"REFUSING: {name} is not set.\n"
            f"The sentinel can detect an outage and not tell anyone, which is "
            f"the exact failure this script exists to end. Set {name} in the "
            f"repository's Actions secrets."
        )
    return value


def build_payload(subject: str, body: str,
                  to: str, sender: str) -> dict:
    """The request, separated from sending so it can be tested without network."""
    recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
    if not recipients:
        raise Misconfigured("REFUSING: ALERT_EMAIL_TO contains no addresses.")
    return {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "text": body,
    }


def send(payload: dict, api_key: str) -> tuple[int, str]:
    """Returns (http_status, body). Never raises for an HTTP error status."""
    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    args = parser.parse_args()

    api_key = _required("RESEND_API_KEY")
    payload = build_payload(args.subject, args.body,
                            _required("ALERT_EMAIL_TO"),
                            _required("ALERT_EMAIL_FROM"))

    # Recipients are printed; the key never is.
    print(f"notifying: {', '.join(payload['to'])}")
    status, body = send(payload, api_key)
    print(f"resend_http_status={status}")
    print(f"resend_response={body[:400]}")

    if 200 <= status < 300:
        try:
            message_id = json.loads(body).get("id", "(none)")
        except ValueError:
            message_id = "(unparseable)"
        print(f"notification_delivered=true message_id={message_id}")
        return 0

    print("notification_delivered=false")
    print("The outage WAS detected and the alert was NOT delivered. "
          "Treat this as a monitoring failure in its own right.")
    return 1


# ── Self-test: no network, no credentials ─────────────────────────────────────

def _self_test() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        print(f"  {'PASS' if condition else 'FAIL'}  {name}"
              + (f"\n        {detail}" if not condition and detail else ""))
        if not condition:
            failures.append(name)

    payload = build_payload("subject", "body",
                            "a@example.com, b@example.com", "s@example.com")
    check("recipients are split and trimmed",
          payload["to"] == ["a@example.com", "b@example.com"],
          f"got {payload['to']}")
    check("the payload carries subject and body",
          payload["subject"] == "subject" and payload["text"] == "body")

    try:
        build_payload("s", "b", "   ,  ", "s@example.com")
        check("an empty recipient list is refused", False,
              "it was accepted, so a typo in the secret would send to nobody")
    except SystemExit:
        check("an empty recipient list is refused", True)

    saved = os.environ.pop("RESEND_API_KEY", None)
    try:
        _required("RESEND_API_KEY")
        check("a missing credential exits rather than warning", False,
              "it returned normally, so a misconfigured secret would look "
              "exactly like a quiet period with no outages")
    except SystemExit:
        check("a missing credential exits rather than warning", True)
    finally:
        if saved is not None:
            os.environ["RESEND_API_KEY"] = saved

    source = open(__file__, encoding="utf-8").read()
    operational = source[:source.index("def _self_test(")]
    check("the API key is never printed",
          "print" not in operational.split("api_key")[1].split("\n")[0],
          "a key echoed into a public Actions log is a disclosed credential")

    print(f"\n{'all self-tests passed' if not failures else f'{len(failures)} failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_self_test() if "--self-test" in sys.argv else main())
