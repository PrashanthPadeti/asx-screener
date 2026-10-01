"""
Cloudflare range drift: detect, never repair
=============================================
The origin now trusts Cloudflare in two places, and both are hand-installed
state generated from one fetch on 1 Oct 2026:

    nginx   set_real_ip_from   — decides whose CF-Connecting-IP is believed
    ufw     allow :80/:443     — decides who may reach the web ports at all

Cloudflare publishes those prefixes and changes them. When a range is added
and neither consumer knows, the symptom is that *some* visitors intermittently
cannot reach the site, from *some* edge locations — which looks like anything
except a stale allowlist. When a range is removed and we still trust it, we
are trusting someone else's address space to assert visitor identity.

Two rules this module exists to enforce, and the first is the subtle one:

    nginx and ufw agreeing with EACH OTHER is not success.

    Both are compared independently against Cloudflare's current published
    set. Two consumers that drifted together would otherwise report clean,
    which is the exact failure mode of a checker that compares a copy to a
    copy.

    A failed fetch is UNVERIFIED, never "no drift".

    An unreachable source proves nothing. Reporting absence of evidence as
    evidence of absence is how a check becomes decorative.

It detects and reports. It performs no ufw or nginx mutation, deliberately:
a bad upstream response, a parsing defect or an unexpected format must not be
able to rewrite the origin firewall. Automated reconciliation is a separate
decision, after this has accumulated evidence.

Pure. No I/O, no connection, no subprocess — so the scheduled gate and the
admin surface share one definition of drift.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

#: Cloudflare's authoritative lists. Fetched by the caller, never here.
SOURCE_V4 = "https://www.cloudflare.com/ips-v4"
SOURCE_V6 = "https://www.cloudflare.com/ips-v6"

#: Sanity floor. Cloudflare has published ~15 IPv4 and ~7 IPv6 prefixes for
#: years; a response with far fewer is a truncated body or an error page that
#: happened to parse, not a shrunken estimate of the internet.
MIN_V4 = 10
MIN_V6 = 5


def normalise(raw: str) -> Optional[str]:
    """A CIDR in canonical form, or None if it is not one.

    Comparison is semantic, not textual. `2400:CB00:0000::/32` and
    `2400:cb00::/32` are the same network, and a checker that compared
    strings would report drift on a formatting change and miss a real one
    hidden behind different spelling.
    """
    text = raw.strip()
    if not text or text.startswith("#"):
        return None
    try:
        return str(ipaddress.ip_network(text, strict=True))
    except ValueError:
        return None


def _split(cidrs: Iterable[str]) -> tuple[set[str], set[str], list[str]]:
    """(ipv4, ipv6, malformed). Families are kept apart on purpose: a missing
    IPv6 range is invisible in a combined count that IPv4 dominates."""
    v4: set[str] = set()
    v6: set[str] = set()
    bad: list[str] = []
    for raw in cidrs:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        canon = normalise(raw)
        if canon is None:
            bad.append(raw.strip())
        elif ipaddress.ip_network(canon).version == 4:
            v4.add(canon)
        else:
            v6.add(canon)
    return v4, v6, bad


# ── Parsers: what each consumer currently believes ───────────────────────────

def parse_published(v4_text: str, v6_text: str) -> tuple[set[str], set[str], list[str]]:
    """Cloudflare's current set, as fetched."""
    v4, _, bad4 = _split(v4_text.splitlines())
    _, v6, bad6 = _split(v6_text.splitlines())
    return v4, v6, bad4 + bad6


_NGINX = re.compile(r"^\s*set_real_ip_from\s+(\S+?)\s*;", re.M)


def parse_nginx(conf_text: str) -> tuple[set[str], set[str], list[str]]:
    """Whose CF-Connecting-IP nginx will believe."""
    return _split(_NGINX.findall(conf_text))


#: `ufw status` renders a source rule as, roughly:
#:     80/tcp                     ALLOW       173.245.48.0/20
#: and the IPv6 form carries a (v6) marker in the left column. The port is
#: taken from the left column rather than assumed, because a rule for an
#: unrelated port must not be counted as web ingress.
_UFW = re.compile(r"^(\d+)/tcp(?:\s+\(v6\))?\s+ALLOW(?:\s+IN)?\s+(\S+)", re.M)


def parse_ufw(status_text: str, port: int) -> tuple[set[str], set[str], list[str]]:
    """Which sources may reach `port`.

    Only rules whose source is a CIDR are considered. `Anywhere` is not a
    range and is reported by the caller as its own condition -- its presence
    means the bypass is open, which is a different and worse finding than
    drift.
    """
    found = [src for p, src in _UFW.findall(status_text) if int(p) == port]
    return _split(found)


def ufw_allows_anywhere(status_text: str, port: int) -> bool:
    """Is the broad allowance back? Worth its own answer: a drift check that
    passed while `Anywhere` was restored would be reporting on the wrong
    question entirely."""
    return any(int(p) == port and src.lower().startswith("anywhere")
               for p, src in _UFW.findall(status_text))


# ── The decision ─────────────────────────────────────────────────────────────

@dataclass
class ConsumerResult:
    name: str
    v4: set[str] = field(default_factory=set)
    v6: set[str] = field(default_factory=set)
    malformed: list[str] = field(default_factory=list)
    anywhere: bool = False

    def missing(self, ev4: set[str], ev6: set[str]) -> list[str]:
        return sorted((ev4 - self.v4) | (ev6 - self.v6))

    def extra(self, ev4: set[str], ev6: set[str]) -> list[str]:
        return sorted((self.v4 - ev4) | (self.v6 - ev6))


def evaluate(published: Optional[tuple[set[str], set[str], list[str]]],
             consumers: list[ConsumerResult],
             fetch_error: str = "") -> dict:
    """current | drift | unverified, with the evidence attached.

    `unverified` is returned whenever the expected set could not be
    established -- a failed fetch, a malformed body, or an implausibly small
    list. It is NOT a pass: the state is unknown, and an unknown state must
    not look like a clean one.
    """
    if published is None or fetch_error:
        return {"state": "unverified",
                "reason": fetch_error or "no published set was supplied",
                "sources": [SOURCE_V4, SOURCE_V6]}

    ev4, ev6, bad = published
    if bad:
        return {"state": "unverified",
                "reason": f"published list contains {len(bad)} malformed "
                          f"entries: {bad[:3]}",
                "sources": [SOURCE_V4, SOURCE_V6]}
    if len(ev4) < MIN_V4 or len(ev6) < MIN_V6:
        return {"state": "unverified",
                "reason": f"published list is implausibly small "
                          f"({len(ev4)} IPv4, {len(ev6)} IPv6); refusing to "
                          f"treat it as authoritative",
                "sources": [SOURCE_V4, SOURCE_V6]}

    details, drifted = [], False
    for c in consumers:
        missing, extra = c.missing(ev4, ev6), c.extra(ev4, ev6)
        if missing or extra or c.malformed or c.anywhere:
            drifted = True
        details.append({
            "consumer": c.name,
            "ipv4": len(c.v4), "ipv6": len(c.v6),
            "missing": missing, "extra": extra,
            "malformed": c.malformed,
            "allows_anywhere": c.anywhere,
        })

    return {
        "state": "drift" if drifted else "current",
        "expected": {"ipv4": len(ev4), "ipv6": len(ev6)},
        "consumers": details,
        "sources": [SOURCE_V4, SOURCE_V6],
    }


def render(result: dict) -> str:
    """The human form, for the scheduled gate's output."""
    lines = []
    if result["state"] == "unverified":
        lines.append("UNVERIFIED — the expected set could not be established")
        lines.append(f"  {result['reason']}")
        lines.append("  This is not 'no drift'. The state is unknown.")
        return "\n".join(lines)

    e = result["expected"]
    lines.append(f"Cloudflare expected: {e['ipv4']} IPv4 / {e['ipv6']} IPv6")
    for c in result["consumers"]:
        lines.append(f"{c['consumer']:<20} {c['ipv4']} IPv4 / {c['ipv6']} IPv6")
    lines.append("")
    for c in result["consumers"]:
        lines.append(f"missing {c['consumer']:<14} {len(c['missing'])}")
        lines.append(f"extra   {c['consumer']:<14} {len(c['extra'])}")
        if c["missing"]:
            lines.append(f"    missing: {', '.join(c['missing'])}")
        if c["extra"]:
            lines.append(f"    extra:   {', '.join(c['extra'])}")
        if c["malformed"]:
            lines.append(f"    malformed: {', '.join(c['malformed'])}")
        if c["allows_anywhere"]:
            lines.append("    ALLOWS ANYWHERE — the origin bypass is open")
    lines.append("")
    lines.append("PASS" if result["state"] == "current" else "DRIFT")
    return "\n".join(lines)
