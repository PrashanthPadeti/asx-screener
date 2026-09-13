"""
cn() against a real frame, because fixtures could not see this one
==================================================================
``average_over`` had ten passing fixtures. ``PERIOD_REQUIREMENT`` had eleven.
Both were correct. And the change that introduced them bound its new
year-series map to ``by_year`` — ten lines below an existing ``by_year`` that
maps fiscal_year to the whole statement row, and which ``cn()`` reads as
``by_year.get(fy - n)``.

After the shadowing, cn() looked an integer year up in a dict keyed by metric
names. It found nothing, every time, and returned None for every horizon CAGR.
Nothing raised. Two structures with compatible interfaces and different
meanings answered each other's questions with a plausible None.

Measured on 2,117 active companies:

    revenue_cagr_5y     1,148 -> 2
    revenue_cagr_10y      981 -> 2
    bvps_cagr_3y        1,461 -> 0
    growth_score        1,592 -> 0

Every unit test passed throughout, because ``average_over`` was handed the
right dict directly in its fixtures and ``cn()`` was never exercised against a
frame at all. This test closes that: it drives the real row builder with a
real multi-year frame and asserts the horizons come out populated.

The second assertion is the tuple/column alignment. build_yearly_rows returns
a positional tuple that must line up with the INSERT column list, and a
silently misaligned pair would write every value into the wrong column.

Requires psycopg2 (yearly_compute imports it at module scope). Run under the
server venv:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_yearly_horizons.py
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# yearly_compute resolves the credential at import. This test never connects —
# it only needs the module — so a placeholder keeps it runnable anywhere
# without putting a real credential near a test.
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://unused/unused")

import pandas as pd  # noqa: E402

from compute.engine import yearly_compute as yc  # noqa: E402

#: Exactly the columns fetch_annual_financials returns.
COLUMNS = [
    "fiscal_year", "period_end_date", "revenue", "gross_profit", "ebitda",
    "ebit", "interest_expense", "net_profit", "eps", "eps_diluted", "dps",
    "dps_franking_pct", "gpm", "opm", "npm", "ebitda_margin", "total_assets",
    "total_equity", "total_current_assets", "total_current_liab", "total_debt",
    "net_debt", "cash_equivalents", "long_term_debt", "retained_earnings",
    "working_capital", "book_value_per_share", "shares_outstanding",
    "trade_receivables", "inventory", "cfo", "capex", "fcf", "equity_raised",
    "cfi", "dividends_paid", "derived_dps", "derived_franking_pct",
]

FIRST_YEAR, LAST_YEAR = 2015, 2025


def frame(years=range(FIRST_YEAR, LAST_YEAR + 1)) -> pd.DataFrame:
    """A company that has reported every year, growing steadily.

    Values compound at 10% so a CAGR is both computable and recognisable —
    a five-year revenue CAGR here is 0.10 exactly, which distinguishes "the
    horizon resolved" from "some number came out".
    """
    rows = []
    for year in years:
        step = year - FIRST_YEAR
        scale = 1.10 ** step
        rows.append({
            "fiscal_year": year,
            "period_end_date": pd.Timestamp(f"{year}-06-30").date(),
            "revenue": 1000.0 * scale,
            "gross_profit": 400.0 * scale,
            "ebitda": 300.0 * scale,
            "ebit": 250.0 * scale,
            "interest_expense": 20.0,
            "net_profit": 150.0 * scale,
            "eps": 1.5 * scale,
            "eps_diluted": 1.5 * scale,
            "dps": 0.5 * scale,
            "dps_franking_pct": 100.0,
            "gpm": 0.40, "opm": 0.25, "npm": 0.15, "ebitda_margin": 0.30,
            "total_assets": 5000.0 * scale,
            "total_equity": 2000.0 * scale,
            "total_current_assets": 1200.0 * scale,
            "total_current_liab": 600.0 * scale,
            "total_debt": 900.0 * scale,
            "net_debt": 700.0 * scale,
            "cash_equivalents": 200.0 * scale,
            "long_term_debt": 600.0 * scale,
            "retained_earnings": 800.0 * scale,
            "working_capital": 600.0 * scale,
            "book_value_per_share": 20.0 * scale,
            "shares_outstanding": 100.0,
            "trade_receivables": 300.0 * scale,
            "inventory": 250.0 * scale,
            "cfo": 280.0 * scale,
            "capex": -80.0 * scale,
            "fcf": 200.0 * scale,
            "equity_raised": 0.0,
            "cfi": -100.0 * scale,
            "dividends_paid": -50.0 * scale,
            "derived_dps": 0.5 * scale,
            "derived_franking_pct": 100.0,
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def prices() -> pd.Series:
    index = pd.date_range(f"{FIRST_YEAR}-01-01", f"{LAST_YEAR}-12-31", freq="D")
    return pd.Series(30.0, index=index)


def insert_columns() -> list[str]:
    """The INSERT column list, read from the module's own source."""
    source = Path(yc.__file__).read_text(encoding="utf-8")
    match = re.search(r"INSERT INTO market\.yearly_metrics\s*\((.*?)\)\s*VALUES",
                      source, re.S)
    assert match, "could not locate the yearly_metrics INSERT column list"
    body = re.sub(r"--.*?$", "", match.group(1), flags=re.M)
    return [c.strip() for c in body.split(",") if c.strip()]


def latest_row() -> dict:
    rows = yc.build_yearly_rows("TST", frame(), prices(), current_shares=100.0)
    assert rows, "the row builder produced nothing for an 11-year company"
    columns = insert_columns()
    assert len(rows[0]) == len(columns), (
        f"tuple has {len(rows[0])} values, INSERT names {len(columns)} columns "
        f"— positional writes would land in the wrong columns")
    by_year = {dict(zip(columns, r))["fiscal_year"]: dict(zip(columns, r))
               for r in rows}
    return by_year[LAST_YEAR]


# ── The horizons resolve at all ──────────────────────────────────────────────

HORIZONS = [
    "revenue_cagr_3y", "revenue_cagr_5y", "revenue_cagr_7y", "revenue_cagr_10y",
    "net_income_cagr_3y", "net_income_cagr_5y",
    "eps_cagr_3y", "eps_cagr_5y",
    "ebitda_cagr_3y", "ebitda_cagr_5y",
    "fcf_cagr_3y", "fcf_cagr_5y",
    "gross_profit_cagr_3y", "gross_profit_cagr_5y",
    "bvps_cagr_3y", "bvps_cagr_5y",
]


def test_every_horizon_is_populated_for_a_company_with_full_history():
    """The regression in one assertion. A company reporting eleven consecutive
    years has every horizon available, including the ten-year one."""
    row = latest_row()
    missing = [h for h in HORIZONS if row.get(h) is None]

    assert not missing, f"horizons absent despite full history: {missing}"


def test_the_rate_is_the_real_rate_not_merely_a_number():
    """Values compound at exactly 10%, so every horizon must return 0.10.
    A wrong exponent — the positional defect this replaced — produces a
    plausible number rather than a missing one, and only the value catches it.
    """
    row = latest_row()
    for horizon in ("revenue_cagr_3y", "revenue_cagr_5y",
                    "revenue_cagr_7y", "revenue_cagr_10y"):
        assert abs(row[horizon] - 0.10) < 1e-6, f"{horizon} = {row[horizon]}"


def test_an_absent_horizon_yields_nothing_rather_than_a_shorter_one():
    """Six years of history cannot produce a ten-year CAGR. It must be absent,
    not annualised over the six years actually available — a correct six-year
    rate is not the claim `revenue_cagr_10y` makes."""
    rows = yc.build_yearly_rows(
        "TST", frame(range(2020, 2026)), prices(), current_shares=100.0)
    columns = insert_columns()
    row = dict(zip(columns, rows[-1]))

    assert row["revenue_cagr_5y"] is not None
    assert row["revenue_cagr_7y"] is None
    assert row["revenue_cagr_10y"] is None


def test_a_gap_in_the_history_does_not_shift_the_window():
    """2018 missing. The ten-year horizon from 2025 needs 2015, which exists,
    so it must still resolve — resolution is by year, not by row position.
    The five-year needs 2020, also present. Only a horizon that lands on the
    missing year is lost."""
    years = [y for y in range(FIRST_YEAR, LAST_YEAR + 1) if y != 2018]
    rows = yc.build_yearly_rows("TST", frame(years), prices(), current_shares=100.0)
    columns = insert_columns()
    row = dict(zip(columns, rows[-1]))

    assert row["revenue_cagr_10y"] is not None, "2015 is present; 2018 is not the anchor"
    assert abs(row["revenue_cagr_10y"] - 0.10) < 1e-6
    assert row["revenue_cagr_7y"] is None, "2018 is the anchor for the 7y horizon"


# ── The rolling averages still work beside them ──────────────────────────────

def test_the_rolling_averages_survive_the_rename():
    """metric_series and by_year are now distinct names. Both paths have to
    work in the same run — that they cannot share a name is exactly the point.
    """
    row = latest_row()
    for metric in ("avg_roe_3y", "avg_roe_5y", "avg_roce_3y", "avg_net_margin_3y"):
        assert row.get(metric) is not None, f"{metric} absent with full history"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
