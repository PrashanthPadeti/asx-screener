#!/usr/bin/env python
"""
What can already be substantiated for a Company Overview?
=========================================================
READ-ONLY. No writes, no DDL. Fetches a handful of companies and reports
which of the thirteen requested sections each available field could serve.

Why this runs before anything is built
--------------------------------------
The decision is to ingest annual reports and extract with citations, which
is a document pipeline, storage, an extraction step and a citation
contract, across ~2,100 companies. Before building that, it is worth
knowing how much of it is unnecessary.

We already pay for EODHD fundamentals and already call that endpoint for
index constituents. Its `General` block commonly carries officers,
employee counts, addresses and sometimes an incorporation date. If it does
for ASX companies, then sections 2, 5, 9 and 11 need no documents at all,
and the pipeline only has to carry the sections that genuinely live in
annual reports: business model and segment revenue, customers, order book,
investments, strategy and outlook.

Getting that wrong in either direction is expensive. Building a PDF
pipeline for data a provider already serves wastes the work; assuming the
provider has it and finding out later leaves the page half-built.

What this does NOT establish
----------------------------
Whether the provider's values are CORRECT, or how current they are. It
reports presence, shape and a sample value. A field that exists is a
candidate, not a source -- the same distinction that made a symbol which
returns data not a symbol that returns the intended index.

Usage:
    PYTHONPATH=/opt/asx-screener/backend \\
      /opt/asx-screener/asx-venv/bin/python \\
      backend/scripts/probe_company_overview_sources.py
    ... --codes PLS,BHP,CBA,CSL     which companies to probe
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app" / "core" / "config.py").exists() else Path.cwd()
if not (BACKEND / "app" / "core" / "config.py").exists():
    sys.exit(f"run this from the backend directory (looked in {BACKEND})")
sys.path.insert(0, str(BACKEND))

#: A deliberate spread: a lithium miner, a diversified major, a bank and a
#: healthcare company. Coverage that holds for BHP and not for a small
#: explorer would be coverage we cannot build a 2,100-company page on, and
#: probing only large caps would hide that.
DEFAULT_CODES = ["PLS", "BHP", "CBA", "CSL", "BRN"]

#: The thirteen requested sections, and the provider fields that could
#: serve each. Mapping stated up front so the output is read against the
#: request rather than against whatever happens to come back.
#: section -> (fields, what those fields do NOT establish)
#:
#: The second element matters. The first version of this mapped section 4
#: to the income statement and section 10 to the industry classification,
#: then reported both as served. An income statement gives totals, not
#: which activities earn the money; an industry label is not a list of
#: competitors; a head-office address is not the countries a company
#: operates in. A field that is adjacent to a question does not answer it.
SECTIONS: dict[str, tuple[list[str], str]] = {
    "1 profile":         (["General.Name", "General.Code", "General.Exchange",
                           "General.Industry", "General.Sector",
                           "General.Description"], ""),
    "2 history/listing": (["General.IPODate", "General.FiscalYearEnd"],
                          "no founding/incorporation date; IPODate is the "
                          "listing date and is not served for every company"),
    "3 core business":   (["General.Description", "General.GicSubIndustry"],
                          "one paragraph and a classification; no products, "
                          "no specialisation detail"),
    "4 business model":  (["General.Description"],
                          "NO SEGMENT REVENUE. The income statement gives "
                          "totals, not which activities contribute most"),
    "5 locations":       (["General.Address", "General.CountryName"],
                          "HEAD OFFICE ONLY. Not operating locations, not "
                          "the countries or regions served"),
    "6 customers":       ([], "nothing"),
    "7 order book":      ([], "nothing"),
    "8 investments":     ([], "nothing"),
    "9 employees":       (["General.FullTimeEmployees"],
                          "a count; no workforce detail"),
    "10 competitors":    (["General.Industry", "General.Sector"],
                          "A CLASSIFICATION, NOT COMPETITORS. No market "
                          "position, no named rivals"),
    "11 management":     (["General.Officers"],
                          "officers as the provider holds them; currency "
                          "unverified"),
    "12 vision":         ([], "nothing"),
    "13 outlook":        ([], "nothing"),
}


def _dig(payload: dict, dotted: str):
    cur = payload
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _describe(value) -> str:
    if value is None:
        return "ABSENT"
    if isinstance(value, dict):
        return f"dict({len(value)} keys): {list(value)[:4]}"
    if isinstance(value, list):
        return f"list({len(value)})"
    text = str(value).strip()
    if not text or text.lower() in ("na", "n/a", "none", "null"):
        return "EMPTY"
    return (text[:70] + "…") if len(text) > 70 else text


def fetch(key: str, code: str):
    import httpx
    try:
        r = httpx.get(f"https://eodhd.com/api/fundamentals/{code}.AU",
                      params={"api_token": key, "fmt": "json"}, timeout=40)
    except Exception as exc:                                   # noqa: BLE001
        return None, f"fetch failed ({type(exc).__name__})"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), "ok"
    except ValueError:
        return None, "unparseable response"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=",".join(DEFAULT_CODES))
    args = ap.parse_args()
    codes = [c.strip().upper() for c in args.codes.split(",") if c.strip()]

    from app.core.config import settings
    key = settings.EODHD_API_KEY
    if not key:
        sys.exit("EODHD_API_KEY is not set")

    payloads = {}
    print("Fetching fundamentals …")
    for code in codes:
        payload, status = fetch(key, code)
        payloads[code] = payload
        top = list(payload) if isinstance(payload, dict) else []
        print(f"  {code:6} {status:16} top-level blocks: {top[:8]}")
    print(f"\n  EODHD requests: {len(codes)}\n")

    print("=" * 78)
    print("PER SECTION — which fields are present, per company")
    print("=" * 78)
    coverage = {}
    for section, (fields, caveat) in SECTIONS.items():
        print(f"\n{section}")
        if caveat:
            print(f"    does NOT establish: {caveat}")
        if not fields:
            print("    no candidate provider field — annual reports or nothing")
            coverage[section] = 0.0
            continue
        # A section is only as served as its WEAKEST field. Summing presence
        # across fields let one field present for everyone carry a section
        # whose other fields were absent for most -- an aggregate hiding its
        # members, which is the defect this codebase keeps finding.
        per_field = []
        for field in fields:
            cells, n = [], 0
            for code in codes:
                p = payloads.get(code)
                val = _dig(p, field) if isinstance(p, dict) else None
                shown = _describe(val)
                cells.append(f"{code}={shown}")
                if shown not in ("ABSENT", "EMPTY"):
                    n += 1
            per_field.append(n / len(codes))
            print(f"    {field}   [{n}/{len(codes)} companies]")
            for c in cells:
                print(f"        {c}")
        coverage[section] = min(per_field)

    print("\n" + "=" * 78)
    print("WHAT THIS CHANGES")
    print("=" * 78)
    covered = [s for s, n in coverage.items() if n == 1.0]
    partial = [s for s, n in coverage.items() if 0 < n < 1.0]
    none_ = [s for s, n in coverage.items() if n == 0]
    print(f"  served for every company probed: {covered or 'none'}")
    print(f"  served for SOME only:            {partial or 'none'}")
    print(f"  no provider field at all:        {none_ or 'none'}")
    print("\n  'Served for some only' is the important row. A section that")
    print("  works for BHP and not for a small explorer cannot be built on")
    print("  for 2,100 companies without saying so per company.")
    print("\n  Presence is not correctness and not currency. A field that")
    print("  exists is a candidate, not a source.")

    # One full General block, so the fields NOT guessed at above are visible
    # too -- the mapping was written before the data was seen.
    first = next((c for c in codes if isinstance(payloads.get(c), dict)), None)
    if first:
        general = payloads[first].get("General", {})
        print(f"\n  Every key EODHD returns in General for {first}:")
        print("   ", json.dumps(sorted(general)[:60], indent=None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
