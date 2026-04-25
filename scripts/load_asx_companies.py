"""
ASX Screener — Load ASX Company List
=====================================
Downloads the full ASX company list (~2,200 stocks) from the ASX website
and inserts them into market.companies.

Usage:
    pip install requests psycopg2-binary python-dotenv pandas
    python scripts/load_asx_companies.py

Source:
    https://www.asx.com.au/asx/research/ASXListedCompanies.csv
    Published by ASX, updated daily.
"""

import os
import sys
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from datetime import date

load_dotenv()

# ── Config ────────────────────────────────────────────────────

ASX_CSV_URL = "https://www.asx.com.au/asx/research/ASXListedCompanies.csv"

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:changeme@localhost:5432/asx_screener"
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

# ASX codes known to be miners/resources
MINING_INDUSTRIES = {
    "Gold Mining", "Silver Mining", "Copper Mining", "Iron Ore Mining",
    "Coal Mining", "Mineral Sands Mining", "Nickel Mining", "Zinc Mining",
    "Lithium Mining", "Uranium Mining", "Bauxite Mining", "Diversified Metals",
    "Diamonds & Gemstones Mining", "Exploration & Mining",
}


def download_asx_list() -> pd.DataFrame:
    """Download and parse ASX listed companies CSV."""
    print(f"Downloading ASX company list from {ASX_CSV_URL} ...")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ASXScreener/1.0)"
    }

    resp = requests.get(ASX_CSV_URL, headers=headers, timeout=30)
    resp.raise_for_status()

    # ASX CSV has 2 header rows — skip first row (title), use second as header
    from io import StringIO
    content = resp.text

    # Find where the real CSV data starts (skip the first description line)
    lines = content.split("\n")
    # First line is: "ASX listed companies as at ..."
    # Second line is: "Company name,ASX code,GICS industry group"
    csv_start = 1  # skip the first description line

    df = pd.read_csv(
        StringIO("\n".join(lines[csv_start:])),
        skipinitialspace=True,
        dtype=str,
    )

    # Clean column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    print(f"  Downloaded {len(df)} companies")
    return df


def transform(df: pd.DataFrame) -> list[dict]:
    """Transform raw CSV rows to company dicts ready for DB insert."""
    companies = []

    for _, row in df.iterrows():
        asx_code = str(row.get("asx_code", "")).strip().upper()
        company_name = str(row.get("company_name", "")).strip()
        gics = str(row.get("gics_industry_group", "")).strip()

        if not asx_code or not company_name or asx_code == "NAN":
            continue

        sector = GICS_TO_SECTOR.get(gics, "Other")
        is_reit = asx_code in KNOWN_REITS or gics == "Real Estate"
        is_miner = gics in MINING_INDUSTRIES or "Mining" in gics or "Resources" in gics

        companies.append({
            "asx_code":     asx_code,
            "company_name": company_name,
            "sector":       sector,
            "industry":     gics if gics and gics != "Not Applic" else None,
            "is_reit":      is_reit,
            "is_miner":     is_miner,
            "listing_date": None,   # Not in ASX CSV — enriched later
            "is_active":    True,
            "data_source":  "asx_csv",
        })

    return companies


def upsert_companies(companies: list[dict], db_url: str) -> None:
    """Upsert all companies into market.companies."""
    print(f"\nConnecting to database...")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    rows = [
        (
            c["asx_code"],
            c["company_name"],
            c["sector"],
            c["industry"],
            c["is_reit"],
            c["is_miner"],
            c["listing_date"],
            c["is_active"],
            c["data_source"],
        )
        for c in companies
    ]

    sql = """
        INSERT INTO market.companies (
            asx_code, company_name, sector, industry,
            is_reit, is_miner, listing_date, is_active, data_source
        )
        VALUES %s
        ON CONFLICT (asx_code) DO UPDATE SET
            company_name = EXCLUDED.company_name,
            sector       = EXCLUDED.sector,
            industry     = EXCLUDED.industry,
            is_reit      = EXCLUDED.is_reit,
            is_miner     = EXCLUDED.is_miner,
            is_active    = EXCLUDED.is_active,
            data_source  = EXCLUDED.data_source,
            updated_at   = NOW()
    """

    print(f"Upserting {len(rows)} companies ...")
    execute_values(cur, sql, rows, page_size=500)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM market.companies WHERE is_active = TRUE")
    count = cur.fetchone()[0]
    print(f"  market.companies now has {count} active companies ✅")

    cur.close()
    conn.close()


def print_summary(companies: list[dict]) -> None:
    """Print a breakdown of what we loaded."""
    df = pd.DataFrame(companies)
    print("\n── Sector Breakdown ─────────────────────────────────────")
    print(df["sector"].value_counts().to_string())
    print(f"\n── REITs: {df['is_reit'].sum()}")
    print(f"── Miners: {df['is_miner'].sum()}")
    print(f"── Total: {len(df)}")
    print("─────────────────────────────────────────────────────────\n")


def main():
    try:
        df = download_asx_list()
        companies = transform(df)
        print_summary(companies)
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
