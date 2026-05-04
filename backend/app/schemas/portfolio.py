"""
Portfolio — Pydantic schemas
"""
from __future__ import annotations
from datetime import date
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, field_validator


# ── Portfolio ─────────────────────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_smsf: bool = False


class PortfolioOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_smsf: bool
    created_at: str


class PortfoliosResponse(BaseModel):
    portfolios: List[PortfolioOut]


# ── Transactions ──────────────────────────────────────────────────────────────

class TransactionAdd(BaseModel):
    asx_code: str
    transaction_type: str          # buy | sell | drp
    transaction_date: date
    shares: float
    price_per_share: float
    brokerage: float = 0.0
    notes: Optional[str] = None

    @field_validator("transaction_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"buy", "sell", "drp"}
        if v.lower() not in allowed:
            raise ValueError(f"transaction_type must be one of {allowed}")
        return v.lower()

    @field_validator("asx_code")
    @classmethod
    def upper_code(cls, v: str) -> str:
        return v.upper().strip()


class TransactionOut(BaseModel):
    id: int
    asx_code: str
    transaction_type: str
    transaction_date: str
    shares: float
    price_per_share: float
    brokerage: float
    total_cost: Optional[float]
    notes: Optional[str]


class TransactionsResponse(BaseModel):
    transactions: List[TransactionOut]


# ── Holdings (computed from transactions) ────────────────────────────────────

class HoldingRow(BaseModel):
    asx_code: str
    company_name: Optional[str]
    sector: Optional[str]
    quantity: float
    avg_cost: float
    cost_basis: float               # quantity × avg_cost
    current_price: Optional[float]
    current_value: Optional[float]  # quantity × current_price
    gain_loss: Optional[float]      # current_value − cost_basis
    gain_loss_pct: Optional[float]  # gain_loss / cost_basis × 100
    dividend_yield: Optional[float]
    annual_income: Optional[float]  # quantity × dps_ttm
    franking_pct: Optional[float]


class PortfolioPerformance(BaseModel):
    portfolio_id: str
    portfolio_name: str
    total_cost: float
    total_value: Optional[float]
    total_gain_loss: Optional[float]
    total_gain_loss_pct: Optional[float]
    annual_income: Optional[float]
    portfolio_yield: Optional[float]   # annual_income / total_value
    holdings: List[HoldingRow]


# ── CSV Import ────────────────────────────────────────────────────────────────

class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[str]
