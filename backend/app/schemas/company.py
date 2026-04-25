"""
Pydantic schemas for market.companies
"""
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class CompanyBase(BaseModel):
    asx_code: str
    company_name: str
    gics_sector: Optional[str] = None
    gics_industry_group: Optional[str] = None
    is_reit: bool = False
    is_miner: bool = False
    status: str = "active"


class CompanyListItem(CompanyBase):
    """Lightweight schema for screener/search results."""
    is_asx200: bool = False
    listing_date: Optional[date] = None

    model_config = {"from_attributes": True}


class CompanyDetail(CompanyBase):
    """Full company detail for company page."""
    isin: Optional[str] = None
    short_name: Optional[str] = None
    gics_industry: Optional[str] = None
    gics_sub_industry: Optional[str] = None
    asx_sector: Optional[str] = None
    company_type: Optional[str] = None

    is_bank: bool = False
    is_insurer: bool = False
    is_asx20: bool = False
    is_asx50: bool = False
    is_asx100: bool = False
    is_asx200: bool = False
    is_asx300: bool = False
    is_all_ords: bool = False

    listing_date: Optional[date] = None
    ipo_price: Optional[float] = None
    financial_year_end: Optional[int] = None
    shares_outstanding: Optional[int] = None
    shares_float: Optional[int] = None

    website: Optional[str] = None
    abn: Optional[str] = None
    domicile: Optional[str] = None
    state: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    employee_count: Optional[int] = None

    primary_commodity: Optional[str] = None
    secondary_commodity: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CompanySearchResult(BaseModel):
    """Minimal schema for autocomplete search."""
    asx_code: str
    company_name: str
    gics_sector: Optional[str] = None
    is_reit: bool = False
    is_miner: bool = False

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    data: list[CompanyListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
