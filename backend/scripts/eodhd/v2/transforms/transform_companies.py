"""
Transform: staging.company_profile → market.companies  (SCD Type 2)
=====================================================================
Reads the latest snapshot from staging.company_profile and applies
SCD Type 2 logic to market.companies:

  - New stock (no current row)  → INSERT with valid_from=today, is_current=TRUE
  - Existing stock, no changes  → UPDATE non-tracked fields in-place
  - Existing stock, tracked field changed → close old version (valid_to, is_current=FALSE),
                                            INSERT new version

SCD2-tracked fields (trigger new version):
  gics_sector, gics_industry_group, gics_industry, gics_sub_industry,
  stock_type, status, fiscal_year_end_month, is_reit, is_miner

Non-tracked (updated in-place):
  company_name, isin, website, description, employee_count,
  is_asx20/50/100/200/300/all_ords

Usage:
    python scripts/eodhd/v2/transforms/transform_companies.py
    python scripts/eodhd/v2/transforms/transform_companies.py --codes BHP CBA
"""

import logging
import os
import sys
import argparse
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

TODAY = date.today()

SCD2_FIELDS = (
    "gics_sector", "gics_industry_group", "gics_industry", "gics_sub_industry",
    "company_type", "status", "fiscal_year_end_month", "is_reit", "is_miner",
)

def sn(v): return None if v is None or str(v).strip() in ("", "None", "N/A") else str(v).strip()
def sb(v): return bool(v) if v is not None else False

FISCAL_MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

def _fiscal_month(fy_end_str) -> int | None:
    if not fy_end_str:
        return None
    s = str(fy_end_str).strip().title()
    return FISCAL_MONTH_MAP.get(s)

STOCK_TYPE_MAP = {
    "common stock": "equity", "ordinary share": "equity",
    "etf": "etf", "exchange traded fund": "etf",
    "fund": "fund",
    "reit": "reit", "real estate investment trust": "reit",
    "stapled": "stapled",
    "lic": "lic", "listed investment company": "lic",
}

def _stock_type(eodhd_type: str | None) -> str:
    if not eodhd_type:
        return "equity"
    return STOCK_TYPE_MAP.get(eodhd_type.lower(), "equity")


def transform_one(cur, row: dict) -> str:
    """
    Apply SCD2 logic for one stock. Returns 'new', 'versioned', 'updated', 'unchanged'.
    """
    asx_code = row["asx_code"]

    # Derive our clean values
    new_vals = {
        "gics_sector":           sn(row.get("sector")),
        "gics_industry_group":   sn(row.get("gic_group")),
        "gics_industry":         sn(row.get("gic_industry")),
        "gics_sub_industry":     sn(row.get("gic_sub_industry")),
        "company_type":          _stock_type(row.get("type")),
        "status":                "active",        # staging doesn't have status; default active
        "fiscal_year_end_month": _fiscal_month(row.get("fiscal_year_end")),
        "is_reit":               "reit" in (sn(row.get("gic_industry")) or "").lower()
                                  or "reit" in (sn(row.get("type")) or "").lower(),
        "is_miner":              any(k in (sn(row.get("gic_industry")) or "").lower()
                                     for k in ("mining", "gold", "metals", "coal")),
        # Non-tracked
        "company_name":          sn(row.get("name")),
        "isin":                  sn(row.get("isin")),
        "website":               sn(row.get("web_url")),
        "description":           sn(row.get("description")),
        "employee_count":        row.get("full_time_employees"),
    }

    # Check for existing current row
    cur.execute("""
        SELECT id, gics_sector, gics_industry_group, gics_industry, gics_sub_industry,
               company_type, status, fiscal_year_end_month, is_reit, is_miner
        FROM market.companies
        WHERE asx_code = %s AND is_current = TRUE
        LIMIT 1
    """, (asx_code,))
    existing = cur.fetchone()

    if existing is None:
        # Brand new stock — insert first version
        cur.execute("""
            INSERT INTO market.companies
                (asx_code, company_name, isin,
                 gics_sector, gics_industry_group, gics_industry, gics_sub_industry,
                 company_type, status, fiscal_year_end_month,
                 is_reit, is_miner,
                 website, description,
                 valid_from, valid_to, is_current, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,TRUE,NOW(),NOW())
        """, (
            asx_code, new_vals["company_name"], new_vals["isin"],
            new_vals["gics_sector"], new_vals["gics_industry_group"],
            new_vals["gics_industry"], new_vals["gics_sub_industry"],
            new_vals["company_type"], new_vals["status"],
            new_vals["fiscal_year_end_month"],
            new_vals["is_reit"], new_vals["is_miner"],
            new_vals["website"], new_vals["description"],
            TODAY,
        ))
        return "new"

    old_id = existing[0]
    old_scd2 = {f: existing[i+1] for i, f in enumerate(SCD2_FIELDS)}
    new_scd2 = {f: new_vals[f] for f in SCD2_FIELDS}

    # Normalise for comparison (handle None vs False for booleans)
    def norm(v): return v if v is not None else (False if isinstance(v, bool) else None)
    changed = any(norm(old_scd2[f]) != norm(new_scd2[f]) for f in SCD2_FIELDS)

    if changed:
        # Close existing version
        cur.execute("""
            UPDATE market.companies
            SET valid_to = %s, is_current = FALSE, updated_at = NOW()
            WHERE id = %s
        """, (TODAY, old_id))
        # Insert new version
        cur.execute("""
            INSERT INTO market.companies
                (asx_code, company_name, isin,
                 gics_sector, gics_industry_group, gics_industry, gics_sub_industry,
                 company_type, status, fiscal_year_end_month,
                 is_reit, is_miner,
                 website, description,
                 valid_from, valid_to, is_current, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,TRUE,NOW(),NOW())
        """, (
            asx_code, new_vals["company_name"], new_vals["isin"],
            new_vals["gics_sector"], new_vals["gics_industry_group"],
            new_vals["gics_industry"], new_vals["gics_sub_industry"],
            new_vals["company_type"], new_vals["status"],
            new_vals["fiscal_year_end_month"],
            new_vals["is_reit"], new_vals["is_miner"],
            new_vals["website"], new_vals["description"],
            TODAY,
        ))
        return "versioned"

    # No SCD2 change — update non-tracked fields in-place
    cur.execute("""
        UPDATE market.companies SET
            company_name = COALESCE(%s, company_name),
            isin = COALESCE(%s, isin),
            website = COALESCE(%s, website),
            description = COALESCE(%s, description),
            updated_at = NOW()
        WHERE id = %s
    """, (
        new_vals["company_name"], new_vals["isin"],
        new_vals["website"], new_vals["description"],
        old_id,
    ))
    return "unchanged"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        cur.execute(f"""
            SELECT asx_code, snapshot_date, code, type, name, exchange,
                   currency_code, country_name, isin, cusip, cik,
                   fiscal_year_end, ipo_date, sector, industry,
                   gic_sector, gic_group, gic_industry, gic_sub_industry,
                   description, address, phone, web_url, full_time_employees, updated_at
            FROM staging.company_profile
            WHERE asx_code IN ({placeholders})
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT asx_code, snapshot_date, code, type, name, exchange,
                   currency_code, country_name, isin, cusip, cik,
                   fiscal_year_end, ipo_date, sector, industry,
                   gic_sector, gic_group, gic_industry, gic_sub_industry,
                   description, address, phone, web_url, full_time_employees, updated_at
            FROM staging.company_profile
            ORDER BY asx_code
        """)

    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    total = len(rows)
    log.info(f"Processing {total} companies from staging.company_profile")

    counts = {"new": 0, "versioned": 0, "unchanged": 0, "error": 0}

    for i, row in enumerate(rows, 1):
        try:
            result = transform_one(cur, row)
            counts[result] += 1
        except Exception as e:
            conn.rollback()
            counts["error"] += 1
            log.warning(f"  {row['asx_code']}: {e}")
            continue

        if i % 200 == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}]  new={counts['new']}  "
                     f"versioned={counts['versioned']}  "
                     f"unchanged={counts['unchanged']}  err={counts['error']}")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — new={counts['new']}  versioned={counts['versioned']}  "
             f"unchanged={counts['unchanged']}  errors={counts['error']}")


if __name__ == "__main__":
    main()
