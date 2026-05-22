"""
ASX Screener — Alert Pydantic Schemas
"""
from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime


# ── Alert type registry ────────────────────────────────────────────────────────

VALID_ALERT_TYPES = {
    # Basic price (Free+)
    "price_above",
    "price_below",
    # % change (Free+)
    "pct_1d_above",
    "pct_1w_above",
    # Legacy (kept for backward compat)
    "pct_change_above",
    "pct_change_below",
    # Fundamental (Pro+)
    "div_yield_above",
    "pe_below",
    # Technical (Pro+)
    "rsi_below_30",
    "rsi_above_70",
    # Event (Pro+)
    "announcement",
    "watchlist_news",
    # AI/Screener (Premium+)
    "screener_match",
}

# Minimum plan required per alert type
ALERT_TYPE_MIN_PLAN: dict[str, str] = {
    "price_above":      "free",
    "price_below":      "free",
    "pct_1d_above":     "free",
    "pct_1w_above":     "free",
    "pct_change_above": "free",   # legacy
    "pct_change_below": "free",   # legacy
    "div_yield_above":  "pro",
    "pe_below":         "pro",
    "rsi_below_30":     "pro",
    "rsi_above_70":     "pro",
    "announcement":     "pro",
    "watchlist_news":   "pro",
    "screener_match":   "premium",
}


# ── Create / Update ────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    asx_code:        str
    alert_type:      str
    threshold_value: float = 0.0
    via_email:       bool  = True
    repeat_mode:     str   = "every_time"   # once | every_time | daily_max

    @field_validator("alert_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in VALID_ALERT_TYPES:
            raise ValueError(f"alert_type must be one of {sorted(VALID_ALERT_TYPES)}")
        return v

    @field_validator("asx_code")
    @classmethod
    def upper_code(cls, v: str) -> str:
        return v.upper().strip()


class AlertUpdate(BaseModel):
    asx_code:        Optional[str]   = None
    alert_type:      Optional[str]   = None
    threshold_value: Optional[float] = None
    via_email:       Optional[bool]  = None
    repeat_mode:     Optional[str]   = None
    is_active:       Optional[bool]  = None

    @field_validator("asx_code")
    @classmethod
    def upper_code(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else None

    @field_validator("alert_type")
    @classmethod
    def valid_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_ALERT_TYPES:
            raise ValueError(f"alert_type must be one of {sorted(VALID_ALERT_TYPES)}")
        return v


# ── Response models ────────────────────────────────────────────────────────────

class AlertOut(BaseModel):
    id:                str
    asx_code:          str
    company_name:      Optional[str]      = None
    alert_type:        str
    threshold_value:   float
    via_email:         bool
    is_active:         bool
    repeat_mode:       str
    trigger_count:     int                = 0
    last_triggered_at: Optional[datetime] = None
    created_at:        Optional[datetime] = None

    model_config = {"from_attributes": True}


class AlertsResponse(BaseModel):
    alerts: List[AlertOut]


# ── Triggered history ──────────────────────────────────────────────────────────

class AlertHistoryItem(BaseModel):
    alert_id:          str
    asx_code:          str
    company_name:      Optional[str]  = None
    alert_type:        str
    threshold_value:   float
    triggered_value:   float
    triggered_at:      datetime
    notification_sent: bool

    model_config = {"from_attributes": True}


class AlertHistoryResponse(BaseModel):
    history: List[AlertHistoryItem]
