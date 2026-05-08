"""
ASX Screener — Load ASX Company List
=====================================
Downloads the full ASX company list (~2,200 stocks) from the ASX website
and inserts them into market.companies.

Usage:
    python3 scripts/load_asx_companies.py

Source:
    https://www.asx.com.au/asx/research/ASXListedCompanies.csv
    Published by ASX, updated daily.
"""

import os
import sys
import csv
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from io import StringIO

load_dotenv()

# ── Config ────────────────────────────────────────────────────

ASX_CSV_URL = "https://www.asx.com.au/asx/research/ASXListedCompanies.csv"

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)

# ── GICS sector → our simplified sector mapping ───────────────
GICS_TO_SECTOR = {
    "Energy":                             "Energy",
    "Materials":                          "Materials",
    "Industrials":                        "Industrials",
    "Consumer Discretionary":             "Consumer Discretionary",
    "Consumer Staples":                   "Consumer Staples",
    "Health Care":                        "Healthcare",
    "Financials":                         "Financials",
    "Information Technology":             "Technology",
    "Communication Services":             "Communication Services",
    "Utilities":                          "Utilities",
    "Real Estate":                        "Real Estate",
    "Not Applic":                         "Other",
}

# ASX codes known to be REITs (A-REITs listed on ASX)
KNOWN_REITS = {
    "GMG", "SCG", "GPT", "MGR", "DXS", "VCX", "BWP", "CLW",
    "CIP", "CHC", "NSR", "HDN", "URW", "GDF", "HMC", "ABP",
    "WPR", "CQR", "SCP", "IDX", "PXA", "AOF", "QAL", "IAP",
    "GDI", "360", "ARF", "BWR", "BPF", "DRI", "HPI", "LCK",
    "MCK", "MOF", "MFF", "OPH", "PPT", "RDC", "SAR", "SIV",
    "SUL", "TCL", "TGR", "VVI", "WEB",
}

MINING_KEYWORDS = {"Mining", "Resources", "Metals", "Gold", "Silver", "Copper",
                   "Iron", "Coal", "Mineral", "Nickel", "Zinc", "Lithium",
                   "Uranium", "Bauxite", "Diamonds", "Exploration"}


def download_asx_list() -> list[dict]:
    """Download and parse ASX listed companies CSV without pandas."""
    print(f"Downloading ASX company list from {ASX_CSV_URL} ...")

    headers = {"User-Agent": "Mozilla/5.0 (compatible; ASXScreener/1.0)"}
    resp = requests.get(ASX_CSV_URL, headers=headers, timeout=30)
    resp.raise_for_status()

    lines = resp.text.splitlines()
    print(f"  First 3 raw lines: {lines[:3]}")

    # Find the header row (contains "ASX code" or "asx code")
    header_idx = 0
    for i, line in enumerate(lines[:5]):
        if "asx" in line.lower() and ("code" in line.lower() or "company" in line.lower()):
            header_idx = i
            break

    csv_lines = "\n".join(lines[header_idx:])
    reader = csv.DictReader(StringIO(csv_lines))
    print(f"  CSV fieldnames: {reader.fieldnames}")

    rows = []
    for row in reader:
        normalised = {}
        for k, v in row.items():
            if k is not None:
                normalised[k.strip().lower().replace(" ", "_")] = (v or "").strip()
        rows.append(normalised)

    if rows:
        print(f"  First row keys: {list(rows[0].keys())}")
        print(f"  First row sample: {rows[0]}")
    print(f"  Downloaded {len(rows)} companies")
    return rows


def transform(rows: list[dict]) -> list[dict]:
    """Transform raw CSV rows to company dicts ready for DB insert."""
    companies = []
    sector_counts: dict[str, int] = {}

    for row in rows:
        asx_code = row.get("asx_code", "").strip().upper()
        company_name = row.get("company_name", "").strip()
        gics = row.get("gics_industry_group", "").strip()

        if not asx_code or not company_name or asx_code == "NAN":
            continue

        sector = GICS_TO_SECTOR.get(gics, "Other")
        is_reit = asx_code in KNOWN_REITS or gics == "Real Estate"
        is_miner = any(kw in gics for kw in MINING_KEYWORDS)

        sector_counts[sector] = sector_counts.get(sector, 0) + 1

        companies.append({
            "asx_code":            asx_code,
            "company_name":        company_name,
            "gics_sector":         sector,
            "gics_industry_group": gics if gics and gics != "Not Applic" else None,
            "is_reit":             is_reit,
            "is_miner":            is_miner,
            "status":              "active",
        })

    print("\n── Sector Breakdown ─────────────────────────────────────")
    for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
        print(f"  {sector:<30} {count}")
    reits = sum(1 for c in companies if c["is_reit"])
    miners = sum(1 for c in companies if c["is_miner"])
    print(f"\n── REITs: {reits}")
    print(f"── Miners: {miners}")
    print(f"── Total: {len(companies)}")
    print("─────────────────────────────────────────────────────────\n")

    return companies


def upsert_companies(companies: list[dict], db_url: str) -> None:
    """Upsert all companies into market.companies."""
    print("Connecting to database...")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    from datetime import date
    today = date.today()
    rows = [
        (
            c["asx_code"],
            c["company_name"],
            c["gics_sector"],
            c["gics_industry_group"],
            c["is_reit"],
            c["is_miner"],
            c["status"],
            True,   # is_current
            today,  # valid_from
        )
        for c in companies
    ]

    sql = """
        INSERT INTO market.companies (
            asx_code, company_name, gics_sector, gics_industry_group,
            is_reit, is_miner, status, is_current, valid_from
        )
        VALUES %s
        ON CONFLICT (asx_code) WHERE is_current = TRUE DO UPDATE SET
            company_name         = EXCLUDED.company_name,
            gics_sector          = EXCLUDED.gics_sector,
            gics_industry_group  = EXCLUDED.gics_industry_group,
            is_reit              = EXCLUDED.is_reit,
            is_miner             = EXCLUDED.is_miner,
            status               = EXCLUDED.status,
            updated_at           = NOW()
    """

    print(f"Upserting {len(rows)} companies ...")
    execute_values(cur, sql, rows, page_size=500)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM market.companies WHERE status = 'active'")
    count = cur.fetchone()[0]
    print(f"  market.companies now has {count} active companies ✅")

    cur.close()
    conn.close()


def main():
    try:
        rows = download_asx_list()
        companies = transform(rows)
        upsert_companies(companies, DB_URL)
        print("Done! ✅\n")
    except requests.RequestException as e:
        print(f"Error downloading ASX list: {e}", file=sys.stderr)
        sys.exit(1)
    except psycopg2.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
