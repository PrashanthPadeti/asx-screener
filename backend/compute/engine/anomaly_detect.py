"""
Anomaly Detection Engine
========================
Scans screener.universe for unusual stock patterns and writes flags to
market.anomalies. Run after the weekly pipeline completes.

Usage:
    python -m compute.engine.anomaly_detect [--dry-run]

Flag types:
    PRICE_EARNINGS_DIVERGENCE  — Price up >20% (3M) while earnings down >20% YoY
    VALUE_GROWTH               — P/E < 15 with revenue growth > 20% YoY
    SHORT_SQUEEZE_RISK         — Short interest jumped > 3pp in one week
    OVERSOLD_QUALITY           — RSI < 30 with Piotroski F-Score >= 7
    OVERBOUGHT_WEAK            — RSI > 75 with Piotroski F-Score <= 2
    HIGH_SHORT_INTEREST        — Short interest > 8% of float
    DIVIDEND_YIELD_SPIKE       — Grossed-up yield > 12% (may signal distress or opportunity)
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ── Flag definitions ──────────────────────────────────────────────────────────

FLAGS: list[dict] = [
    {
        "flag_type":   "PRICE_EARNINGS_DIVERGENCE",
        "severity":    "high",
        "description": "Price rose {return_3m:.0f}% over 3 months while earnings fell {earnings_growth_1y:.0f}% YoY — fundamentals diverging from price",
        "sql": """
            SELECT asx_code, return_3m, earnings_growth_1y
            FROM screener.universe
            WHERE status = 'active'
              AND return_3m        >  0.20
              AND earnings_growth_1y < -0.20
              AND return_3m IS NOT NULL
              AND earnings_growth_1y IS NOT NULL
        """,
    },
    {
        "flag_type":   "VALUE_GROWTH",
        "severity":    "medium",
        "description": "P/E {pe_ratio:.1f}x is low while revenue grew {revenue_growth_1y:.0f}% YoY — potential undervalued grower",
        "sql": """
            SELECT asx_code, pe_ratio, revenue_growth_1y
            FROM screener.universe
            WHERE status = 'active'
              AND pe_ratio            > 0
              AND pe_ratio            < 15
              AND revenue_growth_1y   > 0.20
              AND pe_ratio IS NOT NULL
              AND revenue_growth_1y IS NOT NULL
        """,
    },
    {
        "flag_type":   "SHORT_SQUEEZE_RISK",
        "severity":    "medium",
        "description": "Short interest jumped {short_interest_chg_1w:.1f}pp in one week — elevated squeeze or distribution risk",
        "sql": """
            SELECT asx_code, short_interest_chg_1w
            FROM screener.universe
            WHERE status = 'active'
              AND short_interest_chg_1w > 3
              AND short_interest_chg_1w IS NOT NULL
        """,
    },
    {
        "flag_type":   "OVERSOLD_QUALITY",
        "severity":    "medium",
        "description": "RSI {rsi_14:.0f} — technically oversold, yet Piotroski F-Score {piotroski_f_score}/9 indicates sound financials",
        "sql": """
            SELECT asx_code, rsi_14, piotroski_f_score
            FROM screener.universe
            WHERE status = 'active'
              AND rsi_14            < 30
              AND piotroski_f_score >= 7
              AND rsi_14 IS NOT NULL
              AND piotroski_f_score IS NOT NULL
        """,
    },
    {
        "flag_type":   "OVERBOUGHT_WEAK",
        "severity":    "high",
        "description": "RSI {rsi_14:.0f} — technically overbought, yet Piotroski F-Score {piotroski_f_score}/9 signals weak fundamentals",
        "sql": """
            SELECT asx_code, rsi_14, piotroski_f_score
            FROM screener.universe
            WHERE status = 'active'
              AND rsi_14            > 75
              AND piotroski_f_score <= 2
              AND rsi_14 IS NOT NULL
              AND piotroski_f_score IS NOT NULL
        """,
    },
    {
        "flag_type":   "HIGH_SHORT_INTEREST",
        "severity":    "high",
        "description": "{short_pct:.1f}% of float sold short — significant bearish positioning",
        "sql": """
            SELECT asx_code, short_pct
            FROM screener.universe
            WHERE status = 'active'
              AND short_pct > 8
              AND short_pct IS NOT NULL
        """,
    },
    {
        "flag_type":   "DIVIDEND_YIELD_SPIKE",
        "severity":    "medium",
        "description": "Grossed-up yield {grossed_up_yield:.1f}% — unusually high; verify dividend is sustainable",
        "sql": """
            SELECT asx_code, grossed_up_yield * 100 AS grossed_up_yield
            FROM screener.universe
            WHERE status = 'active'
              AND grossed_up_yield > 0.12
              AND grossed_up_yield IS NOT NULL
        """,
    },
]


# ── Runner ────────────────────────────────────────────────────────────────────

async def run(dry_run: bool = False) -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:

        inserted = 0
        resolved = 0

        # Collect all codes with at least one flag this run
        flagged_codes: dict[str, set[str]] = {}  # code → set of flag_types

        for flag in FLAGS:
            flag_type = flag["flag_type"]
            severity  = flag["severity"]
            desc_tpl  = flag["description"]

            rows = (await session.execute(text(flag["sql"]))).mappings().all()
            log.info("%-30s → %d matches", flag_type, len(rows))

            for row in rows:
                code = row["asx_code"]
                # Format description with available columns
                try:
                    desc = desc_tpl.format(**{k: (v or 0) for k, v in row.items()})
                except (KeyError, ValueError):
                    desc = desc_tpl

                flagged_codes.setdefault(code, set()).add(flag_type)

                if not dry_run:
                    await session.execute(text("""
                        INSERT INTO market.anomalies
                            (asx_code, flag_type, description, severity, is_active, detected_at)
                        VALUES
                            (:code, :flag_type, :description, :severity, TRUE, NOW())
                        ON CONFLICT (asx_code, flag_type)
                        DO UPDATE SET
                            description = EXCLUDED.description,
                            severity    = EXCLUDED.severity,
                            is_active   = TRUE,
                            detected_at = NOW(),
                            resolved_at = NULL
                    """), {
                        "code":        code,
                        "flag_type":   flag_type,
                        "description": desc,
                        "severity":    severity,
                    })
                    inserted += 1

        # Resolve (deactivate) flags that no longer apply
        if not dry_run and flagged_codes:
            # Build the set of (code, flag_type) pairs that are still active
            active_pairs = [
                {"code": code, "flag_type": ft}
                for code, fts in flagged_codes.items()
                for ft in fts
            ]
            # Deactivate any flag NOT in the current active set
            known_flag_types = [f["flag_type"] for f in FLAGS]
            await session.execute(text("""
                UPDATE market.anomalies
                SET is_active = FALSE, resolved_at = NOW()
                WHERE is_active = TRUE
                  AND flag_type = ANY(:flag_types)
                  AND NOT EXISTS (
                      SELECT 1 FROM (VALUES {placeholders}) AS v(c, ft)
                      WHERE v.c = market.anomalies.asx_code
                        AND v.ft = market.anomalies.flag_type
                  )
            """.format(
                placeholders=", ".join(f"(:c{i}, :ft{i})" for i in range(len(active_pairs)))
            )), {
                "flag_types": known_flag_types,
                **{f"c{i}":  p["code"]      for i, p in enumerate(active_pairs)},
                **{f"ft{i}": p["flag_type"] for i, p in enumerate(active_pairs)},
            })
            resolved += 1

        if not dry_run:
            await session.commit()

        total_active = sum(len(v) for v in flagged_codes.values())
        log.info(
            "Done — %d flags upserted, active across %d stocks%s",
            inserted, len(flagged_codes),
            " [DRY RUN — nothing written]" if dry_run else "",
        )

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASX Anomaly Detector")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
