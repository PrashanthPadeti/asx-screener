"""
Pydantic schemas for the Screener API
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum


class FilterOperator(str, Enum):
    gt  = "gt"    # greater than
    gte = "gte"   # greater than or equal
    lt  = "lt"    # less than
    lte = "lte"   # less than or equal
    eq  = "eq"    # equal
    neq = "neq"   # not equal
    in_ = "in"    # in list


class ScreenerFilter(BaseModel):
    field:    str
    operator: FilterOperator
    value:    Any   # number, string, or list


class ScreenerRequest(BaseModel):
    filters:    list[ScreenerFilter] = Field(default=[], description="List of filter conditions")
    sort_by:    str                  = Field(default="market_cap", description="Column to sort by")
    sort_dir:   str                  = Field(default="desc", description="asc | desc")
    page:       int                  = Field(default=1, ge=1)
    page_size:  int                  = Field(default=50, ge=1, le=200)

    model_config = {
        "json_schema_extra": {
            "example": {
                "filters": [
                    {"field": "sector",      "operator": "eq",  "value": "Materials"},
                    {"field": "close",       "operator": "gte", "value": 1.0},
                    {"field": "volume_avg",  "operator": "gte", "value": 100000},
                ],
                "sort_by":   "close",
                "sort_dir":  "desc",
                "page":      1,
                "page_size": 50,
            }
        }
    }


class ScreenerRow(BaseModel):
    # Company
    asx_code:       str
    company_name:   str
    gics_sector:    Optional[str] = None
    is_reit:        bool = False
    is_miner:       bool = False
    is_asx200:      bool = False

    # Latest price (from daily_prices)
    close:          Optional[float] = None
    open:           Optional[float] = None
    high:           Optional[float] = None
    low:            Optional[float] = None
    volume:         Optional[int]   = None
    change_pct:     Optional[float] = None   # 1-day % change
    high_52w:       Optional[float] = None
    low_52w:        Optional[float] = None

    # From computed_metrics (populated after compute engine runs)
    market_cap:     Optional[float] = None
    pe_ratio:       Optional[float] = None
    pb_ratio:       Optional[float] = None
    dividend_yield: Optional[float] = None
    grossed_up_yield: Optional[float] = None
    roe:            Optional[float] = None
    debt_to_equity: Optional[float] = None
    revenue_growth_1y: Optional[float] = None
    piotroski_score: Optional[int]  = None

    model_config = {"from_attributes": True}


class ScreenerResponse(BaseModel):
    data:        list[ScreenerRow]
    total:       int
    page:        int
    page_size:   int
    total_pages: int
    filters_applied: int
