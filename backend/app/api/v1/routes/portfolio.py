"""
ASX Screener — Portfolio Routes
=================================
All endpoints require authentication.

GET    /portfolio                          — list user's portfolios
POST   /portfolio                          — create portfolio
DELETE /portfolio/{id}                     — delete portfolio
GET    /portfolio/{id}/performance         — holdings + live P&L
GET    /portfolio/{id}/transactions        — full transaction history
POST   /portfolio/{id}/transactions        — add a transaction
DELETE /portfolio/{id}/transactions/{txn_id} — delete a transaction
POST   /portfolio/{id}/import/holdings     — CSV import (holdings format)
POST   /portfolio/{id}/import/transactions — CSV import (transactions format)
"""
import csv
import io
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.plans import get_limits
from app.db.session import get_db
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioOut,
    PortfoliosResponse,
    TransactionAdd,
    TransactionOut,
    TransactionsResponse,
    HoldingRow,
    PortfolioPerformance,
    ImportResult,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_portfolio_or_404(portfolio_id: str, user_id: str, db: AsyncSession) -> dict:
    row = (await db.execute(
        text("SELECT id, name, description, is_smsf, created_at FROM users.portfolios WHERE id = :pid AND user_id = :uid"),
        {"pid": portfolio_id, "uid": user_id},
    )).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return row


def _compute_holdings(txn_rows) -> dict[str, dict]:
    """
    Compute current holdings from transaction list.
    Returns {asx_code: {quantity, avg_cost, total_cost}}.
    Sells reduce quantity. avg_cost uses weighted average of buys only.
    """
    holdings: dict[str, dict] = {}
    for r in txn_rows:
        code  = r["asx_code"]
        ttype = r["transaction_type"]
        qty   = float(r["shares"])
        price = float(r["price_per_share"])
        brok  = float(r["brokerage"] or 0)

        if code not in holdings:
            holdings[code] = {"quantity": 0.0, "total_buy_cost": 0.0, "total_buy_qty": 0.0}

        h = holdings[code]
        if ttype in ("buy", "drp"):
            cost = qty * price + brok
            h["total_buy_cost"] += cost
            h["total_buy_qty"]  += qty
            h["quantity"]       += qty
        elif ttype == "sell":
            h["quantity"] -= qty

    # Remove fully sold positions, compute avg_cost
    result = {}
    for code, h in holdings.items():
        qty = round(h["quantity"], 4)
        if qty <= 0:
            continue
        avg = (h["total_buy_cost"] / h["total_buy_qty"]) if h["total_buy_qty"] > 0 else 0
        result[code] = {"quantity": qty, "avg_cost": avg, "cost_basis": qty * avg}
    return result


# ── List portfolios ───────────────────────────────────────────────────────────

@router.get("", response_model=PortfoliosResponse)
async def list_portfolios(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        text("SELECT id, name, description, is_smsf, created_at FROM users.portfolios WHERE user_id = :uid ORDER BY created_at ASC"),
        {"uid": current_user["id"]},
    )).mappings().all()
    return PortfoliosResponse(portfolios=[
        PortfolioOut(
            id=str(r["id"]),
            name=r["name"],
            description=r["description"],
            is_smsf=r["is_smsf"],
            created_at=r["created_at"].isoformat(),
        ) for r in rows
    ])


# ── Create portfolio ──────────────────────────────────────────────────────────

@router.post("", response_model=PortfolioOut, status_code=201)
async def create_portfolio(
    body: PortfolioCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Limit: free users max 3 portfolios
    count = (await db.execute(
        text("SELECT COUNT(*) FROM users.portfolios WHERE user_id = :uid"),
        {"uid": current_user["id"]},
    )).scalar()
    limit = get_limits(current_user.get("plan", "free"))["portfolios"]
    if (count or 0) >= limit:
        raise HTTPException(status_code=403, detail=f"Portfolio limit reached ({limit} for your plan)")

    row = (await db.execute(
        text("""
            INSERT INTO users.portfolios (user_id, name, description, is_smsf)
            VALUES (:uid, :name, :desc, :smsf)
            RETURNING id, name, description, is_smsf, created_at
        """),
        {"uid": current_user["id"], "name": body.name, "desc": body.description, "smsf": body.is_smsf},
    )).mappings().one()
    await db.commit()
    return PortfolioOut(
        id=str(row["id"]),
        name=row["name"],
        description=row["description"],
        is_smsf=row["is_smsf"],
        created_at=row["created_at"].isoformat(),
    )


# ── Delete portfolio ──────────────────────────────────────────────────────────

@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_portfolio_or_404(portfolio_id, current_user["id"], db)
    await db.execute(
        text("DELETE FROM users.portfolios WHERE id = :pid"),
        {"pid": portfolio_id},
    )
    await db.commit()


# ── Performance (live P&L) ────────────────────────────────────────────────────

@router.get("/{portfolio_id}/performance", response_model=PortfolioPerformance)
async def get_performance(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_portfolio_or_404(portfolio_id, current_user["id"], db)

    # Fetch all transactions ordered oldest → newest for correct avg cost
    txn_rows = (await db.execute(
        text("""
            SELECT asx_code, transaction_type, shares, price_per_share, brokerage
            FROM users.portfolio_transactions
            WHERE portfolio_id = :pid
            ORDER BY transaction_date ASC, id ASC
        """),
        {"pid": portfolio_id},
    )).mappings().all()

    holdings = _compute_holdings(txn_rows)

    if not holdings:
        return PortfolioPerformance(
            portfolio_id=portfolio_id,
            portfolio_name=p["name"],
            total_cost=0, total_value=None, total_gain_loss=None,
            total_gain_loss_pct=None, annual_income=None, portfolio_yield=None,
            holdings=[],
        )

    # Enrich with live data from screener.universe
    codes = list(holdings.keys())
    # Use individual placeholders — asyncpg doesn't coerce Python lists in text() queries
    placeholders = ', '.join(f':c{i}' for i in range(len(codes)))
    code_params  = {f'c{i}': code for i, code in enumerate(codes)}
    universe_rows = (await db.execute(
        text(f"""
            SELECT asx_code, company_name, sector, price, dps_ttm, dividend_yield, franking_pct
            FROM screener.universe
            WHERE asx_code IN ({placeholders}) AND status = 'Active'
        """),
        code_params,
    )).mappings().all()
    live = {r["asx_code"]: r for r in universe_rows}

    rows: list[HoldingRow] = []
    total_cost = total_value = total_income = 0.0

    for code, h in sorted(holdings.items()):
        qty       = h["quantity"]
        avg_cost  = h["avg_cost"]
        cost_basis = h["cost_basis"]
        total_cost += cost_basis

        u = live.get(code)
        cur_price   = float(u["price"])         if u and u["price"]    is not None else None
        cur_value   = qty * cur_price            if cur_price is not None else None
        gain_loss   = (cur_value - cost_basis)   if cur_value is not None else None
        gain_pct    = (gain_loss / cost_basis * 100) if (gain_loss is not None and cost_basis > 0) else None
        dps         = float(u["dps_ttm"])        if u and u["dps_ttm"] is not None else None
        ann_income  = qty * dps                  if dps is not None else None
        d_yield     = float(u["dividend_yield"]) if u and u["dividend_yield"] is not None else None
        franking    = float(u["franking_pct"])   if u and u["franking_pct"] is not None else None

        if cur_value is not None:
            total_value = (total_value or 0) + cur_value
        if ann_income is not None:
            total_income = (total_income or 0) + ann_income

        rows.append(HoldingRow(
            asx_code=code,
            company_name=u["company_name"] if u else None,
            sector=u["sector"] if u else None,
            quantity=qty,
            avg_cost=avg_cost,
            cost_basis=cost_basis,
            current_price=cur_price,
            current_value=cur_value,
            gain_loss=gain_loss,
            gain_loss_pct=gain_pct,
            dividend_yield=d_yield,
            annual_income=ann_income,
            franking_pct=franking,
        ))

    total_gl      = (total_value - total_cost)   if total_value is not None else None
    total_gl_pct  = (total_gl / total_cost * 100) if (total_gl is not None and total_cost > 0) else None
    port_yield    = (total_income / total_value * 100) if (total_income and total_value) else None

    return PortfolioPerformance(
        portfolio_id=portfolio_id,
        portfolio_name=p["name"],
        total_cost=total_cost,
        total_value=total_value,
        total_gain_loss=total_gl,
        total_gain_loss_pct=total_gl_pct,
        annual_income=total_income if total_income else None,
        portfolio_yield=port_yield,
        holdings=rows,
    )


# ── Transaction list ──────────────────────────────────────────────────────────

@router.get("/{portfolio_id}/transactions", response_model=TransactionsResponse)
async def list_transactions(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_portfolio_or_404(portfolio_id, current_user["id"], db)
    rows = (await db.execute(
        text("""
            SELECT id, asx_code, transaction_type, transaction_date,
                   shares, price_per_share, brokerage, total_cost, notes
            FROM users.portfolio_transactions
            WHERE portfolio_id = :pid
            ORDER BY transaction_date DESC, id DESC
        """),
        {"pid": portfolio_id},
    )).mappings().all()
    return TransactionsResponse(transactions=[
        TransactionOut(
            id=r["id"],
            asx_code=r["asx_code"],
            transaction_type=r["transaction_type"],
            transaction_date=str(r["transaction_date"]),
            shares=float(r["shares"]),
            price_per_share=float(r["price_per_share"]),
            brokerage=float(r["brokerage"] or 0),
            total_cost=float(r["total_cost"]) if r["total_cost"] is not None else None,
            notes=r["notes"],
        ) for r in rows
    ])


# ── Add transaction ───────────────────────────────────────────────────────────

@router.post("/{portfolio_id}/transactions", response_model=TransactionOut, status_code=201)
async def add_transaction(
    portfolio_id: str,
    body: TransactionAdd,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_portfolio_or_404(portfolio_id, current_user["id"], db)
    total = body.shares * body.price_per_share + body.brokerage
    row = (await db.execute(
        text("""
            INSERT INTO users.portfolio_transactions
                (portfolio_id, asx_code, transaction_type, transaction_date,
                 shares, price_per_share, brokerage, total_cost, notes)
            VALUES (:pid, :code, :ttype, :tdate, :shares, :price, :brok, :total, :notes)
            RETURNING id, asx_code, transaction_type, transaction_date,
                      shares, price_per_share, brokerage, total_cost, notes
        """),
        {
            "pid": portfolio_id, "code": body.asx_code, "ttype": body.transaction_type,
            "tdate": body.transaction_date, "shares": body.shares,
            "price": body.price_per_share, "brok": body.brokerage,
            "total": total, "notes": body.notes,
        },
    )).mappings().one()
    await db.commit()
    return TransactionOut(
        id=row["id"],
        asx_code=row["asx_code"],
        transaction_type=row["transaction_type"],
        transaction_date=str(row["transaction_date"]),
        shares=float(row["shares"]),
        price_per_share=float(row["price_per_share"]),
        brokerage=float(row["brokerage"] or 0),
        total_cost=float(row["total_cost"]) if row["total_cost"] is not None else None,
        notes=row["notes"],
    )


# ── Delete transaction ────────────────────────────────────────────────────────

@router.delete("/{portfolio_id}/transactions/{txn_id}", status_code=204)
async def delete_transaction(
    portfolio_id: str,
    txn_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_portfolio_or_404(portfolio_id, current_user["id"], db)
    result = await db.execute(
        text("DELETE FROM users.portfolio_transactions WHERE id = :tid AND portfolio_id = :pid"),
        {"tid": txn_id, "pid": portfolio_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.commit()


# ── CSV Import — holdings format ──────────────────────────────────────────────

@router.post("/{portfolio_id}/import/holdings", response_model=ImportResult)
async def import_holdings_csv(
    portfolio_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Expected CSV columns: asx_code, quantity, avg_cost, purchase_date (optional)
    Creates one BUY transaction per row using avg_cost as the price.
    """
    await _get_portfolio_or_404(portfolio_id, current_user["id"], db)

    content = (await file.read()).decode("utf-8-sig")
    reader  = csv.DictReader(io.StringIO(content))

    imported = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):
        try:
            code  = row.get("asx_code", "").strip().upper()
            qty   = float(row.get("quantity", "").strip())
            cost  = float(row.get("avg_cost", "").strip())
            raw_date = row.get("purchase_date", "").strip() or "2000-01-01"
            txn_date = date.fromisoformat(raw_date)

            if not code or qty <= 0 or cost <= 0:
                raise ValueError("asx_code, quantity, and avg_cost are required and must be positive")

            await db.execute(
                text("""
                    INSERT INTO users.portfolio_transactions
                        (portfolio_id, asx_code, transaction_type, transaction_date,
                         shares, price_per_share, brokerage, total_cost)
                    VALUES (:pid, :code, 'buy', :tdate, :qty, :price, 0, :total)
                """),
                {"pid": portfolio_id, "code": code, "tdate": txn_date,
                 "qty": qty, "price": cost, "total": qty * cost},
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
            skipped += 1

    await db.commit()
    return ImportResult(imported=imported, skipped=skipped, errors=errors[:20])


# ── CSV Import — transactions format ─────────────────────────────────────────

@router.post("/{portfolio_id}/import/transactions", response_model=ImportResult)
async def import_transactions_csv(
    portfolio_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Expected CSV columns: date, asx_code, type, quantity, price, brokerage (optional)
    Supports Sharesight-style exports.
    """
    await _get_portfolio_or_404(portfolio_id, current_user["id"], db)

    content = (await file.read()).decode("utf-8-sig")
    reader  = csv.DictReader(io.StringIO(content))

    imported = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):
        try:
            # Flexible column name matching
            code  = (row.get("asx_code") or row.get("code") or row.get("symbol") or "").strip().upper()
            ttype = (row.get("type") or row.get("transaction_type") or "buy").strip().lower()
            qty   = float((row.get("quantity") or row.get("shares") or "0").strip())
            price = float((row.get("price") or row.get("price_per_share") or "0").strip())
            brok  = float((row.get("brokerage") or row.get("commission") or "0").strip())
            raw_date = (row.get("date") or row.get("transaction_date") or "").strip()
            txn_date = date.fromisoformat(raw_date)

            if ttype not in ("buy", "sell", "drp"):
                ttype = "buy"
            if not code or qty <= 0 or price <= 0:
                raise ValueError("asx_code, quantity, and price are required and must be positive")

            total = qty * price + (brok if ttype == "buy" else -brok)
            await db.execute(
                text("""
                    INSERT INTO users.portfolio_transactions
                        (portfolio_id, asx_code, transaction_type, transaction_date,
                         shares, price_per_share, brokerage, total_cost)
                    VALUES (:pid, :code, :ttype, :tdate, :qty, :price, :brok, :total)
                """),
                {"pid": portfolio_id, "code": code, "ttype": ttype, "tdate": txn_date,
                 "qty": qty, "price": price, "brok": brok, "total": total},
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
            skipped += 1

    await db.commit()
    return ImportResult(imported=imported, skipped=skipped, errors=errors[:20])
