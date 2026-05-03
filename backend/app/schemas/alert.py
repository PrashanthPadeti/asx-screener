"""
ASX Screener — Alert Pydantic Schemas
"""
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


VALID_ALERT_TYPES = {
    "price_above",
    "price_below",
    "pct_change_above",   # 1-day % change exceeds threshold
    "pct_change_below",
}


class AlertCreate(BaseModel):
    asx_code:        str
    alert_type:      str
    threshold_value: float
    via_email:       bool = True
    repeat_mode:     str  = "every_time"   # once | every_time | daily_max

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


class AlertOut(BaseModel):
    id:               str
    asx_code:         str
    alert_type:       str
    threshold_value:  float
    via_email:        bool
    is_active:        bool
    repeat_mode:      str
    trigger_count:    int           = 0
    last_triggered_at: Optional[datetime] = None
    created_at:       Optional[datetime]  = None

    model_config = {"from_attributes": True}


class AlertsResponse(BaseModel):
    alerts: list[AlertOut]
