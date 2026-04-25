# Document 11 — API Design (FastAPI)
# ASX Screener Platform — Backend API Specification
# FastAPI · REST + WebSocket · Auth · Rate Limiting · OpenAPI

---

## Table of Contents

1. [API Overview & Conventions](#1-api-overview--conventions)
2. [Authentication & Middleware](#2-authentication--middleware)
3. [Rate Limiting Strategy](#3-rate-limiting-strategy)
4. [Endpoint Reference](#4-endpoint-reference)
   - 4.1 Auth
   - 4.2 Screener
   - 4.3 Stocks
   - 4.4 Financials
   - 4.5 Watchlists
   - 4.6 Portfolio
   - 4.7 Alerts
   - 4.8 Community Screens
   - 4.9 Market Data
   - 4.10 AI / Claude
   - 4.11 Admin / Internal
5. [WebSocket Endpoints](#5-websocket-endpoints)
6. [Request / Response Schemas (Pydantic)](#6-request--response-schemas-pydantic)
7. [Error Handling](#7-error-handling)
8. [FastAPI Application Structure](#8-fastapi-application-structure)
9. [Caching Strategy](#9-caching-strategy)
10. [API Versioning](#10-api-versioning)

---

## 1. API Overview & Conventions

```
Base URL (production):   https://api.asxscreener.com.au/v1
Base URL (staging):      https://api-staging.asxscreener.com.au/v1
Base URL (local dev):    http://localhost:8000/v1

Protocol:    HTTPS only (TLS 1.3)
Format:      JSON (Content-Type: application/json)
Auth:        Bearer JWT (short-lived) + Refresh Token (httpOnly cookie)
Docs:        /docs (Swagger UI) · /redoc (ReDoc) · /openapi.json
Health:      /health · /ready · /metrics (Prometheus)
```

### Naming Conventions

```
Resources:     plural nouns               /stocks, /watchlists, /alerts
Identifiers:   ticker (uppercase) or UUID /stocks/BHP, /watchlists/uuid
Actions:       POST to sub-resource       POST /alerts/{id}/snooze
Query params:  snake_case                 ?sort_by=pe_ratio&order=asc
Response keys: snake_case                 { "market_cap": 218400 }
Dates:         ISO 8601                   "2026-04-20"
Timestamps:    ISO 8601 with TZ           "2026-04-20T16:00:00+10:00"
Money:         AUD cents (integer) or     { "price_cents": 4520 }
               AUD float with 4 dp        { "price": 45.2000 }
```

### Pagination

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total_items": 47,
    "total_pages": 2,
    "has_next": true,
    "has_prev": false
  }
}
```

Params: `?page=1&page_size=25` (max page_size: 200 for free, 1000 for Pro/API)

---

## 2. Authentication & Middleware

### JWT Token Strategy

```
Access Token:   JWT, 15-minute expiry, Bearer header
Refresh Token:  Opaque UUID, 30-day expiry, httpOnly Secure cookie
API Key:        Long-lived, rate-limited separately (Premium tier only)

Token payload:
{
  "sub": "user-uuid-here",
  "email": "user@example.com",
  "plan": "pro",           // free | pro | premium
  "iat": 1745123456,
  "exp": 1745124356
}
```

### Middleware Stack (order matters)

```python
# main.py — middleware applied bottom-up (last added = outermost)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # ["https://asxscreener.com.au"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RequestIDMiddleware)   # X-Request-ID header
app.add_middleware(LoggingMiddleware)     # structured JSON logs → Sentry
app.add_middleware(RateLimitMiddleware)   # Redis-backed sliding window
```

### Auth Dependency

```python
# deps/auth.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

bearer_scheme = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def require_pro(user: User = Depends(get_current_user)) -> User:
    if user.plan not in ("pro", "premium"):
        raise HTTPException(status_code=403, detail="Pro subscription required")
    return user

async def require_premium(user: User = Depends(get_current_user)) -> User:
    if user.plan != "premium":
        raise HTTPException(status_code=403, detail="Premium subscription required")
    return user

# Optional auth — returns None if no token provided (for public endpoints)
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
```

---

## 3. Rate Limiting Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│  RATE LIMITS (per IP for anonymous, per user for authenticated)  │
├──────────────┬─────────────┬────────────┬────────────┬──────────┤
│  Endpoint    │  Anonymous  │   Free     │    Pro     │ Premium  │
│  Group       │             │            │            │  / API   │
├──────────────┼─────────────┼────────────┼────────────┼──────────┤
│ Auth         │ 10/min      │ 10/min     │ 10/min     │ 10/min   │
│ Screener     │ 3/min       │ 20/min     │ 100/min    │ 500/min  │
│ Stock Detail │ 30/min      │ 60/min     │ 300/min    │ 1000/min │
│ Watchlists   │ —           │ 30/min     │ 100/min    │ 500/min  │
│ Portfolio    │ —           │ 20/min     │ 60/min     │ 200/min  │
│ AI Chat      │ —           │ —          │ 10/min     │ 30/min   │
│ Bulk/Export  │ —           │ 2/hour     │ 20/hour    │ 100/hour │
│ API Key      │ —           │ —          │ —          │ 10K/day  │
└──────────────┴─────────────┴────────────┴────────────┴──────────┘

Implementation: Redis sliding window (token bucket per user+endpoint_group)
Headers returned:
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 87
  X-RateLimit-Reset: 1745124000   (Unix timestamp)
  Retry-After: 13                 (seconds, only on 429)
```

```python
# middleware/rate_limit.py — Redis sliding window

async def check_rate_limit(
    redis: Redis,
    key: str,
    limit: int,
    window_seconds: int = 60,
) -> tuple[bool, int, int]:
    """Returns (allowed, remaining, reset_ts)"""
    now = time.time()
    window_start = now - window_seconds

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)       # remove old entries
    pipe.zadd(key, {str(now): now})                   # add current request
    pipe.zcard(key)                                   # count in window
    pipe.expire(key, window_seconds)
    _, _, count, _ = await pipe.execute()

    allowed = count <= limit
    remaining = max(0, limit - count)
    reset_ts = int(now + window_seconds)
    return allowed, remaining, reset_ts
```

---

## 4. Endpoint Reference

### 4.1 Auth Endpoints

```
POST   /v1/auth/register          Register new user
POST   /v1/auth/login             Login, returns JWT + sets refresh cookie
POST   /v1/auth/refresh           Use refresh cookie to get new access token
POST   /v1/auth/logout            Invalidate refresh token
POST   /v1/auth/forgot-password   Send reset email
POST   /v1/auth/reset-password    Reset with token from email
POST   /v1/auth/google            OAuth2 with Google
GET    /v1/auth/me                Current user profile
PATCH  /v1/auth/me                Update profile (name, timezone, etc.)
DELETE /v1/auth/me                Delete account (GDPR)
POST   /v1/auth/api-key           Generate API key [Premium]
DELETE /v1/auth/api-key           Revoke API key [Premium]
```

#### POST /v1/auth/register

```
Request:
{
  "email": "user@example.com",
  "password": "securepassword123",
  "full_name": "Jane Smith",
  "plan": "free"                    // free | pro | premium
}

Response 201:
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "Jane Smith",
    "plan": "free",
    "created_at": "2026-04-20T10:00:00+10:00"
  },
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
// Also sets: Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Strict
```

#### POST /v1/auth/login

```
Request:
{
  "email": "user@example.com",
  "password": "securepassword123"
}

Response 200: (same as register)

Errors:
  401 { "detail": "Invalid credentials" }
  429 { "detail": "Too many login attempts. Try again in 15 minutes." }
```

---

### 4.2 Screener Endpoints

```
POST   /v1/screener/run           Run a screen, returns matching stocks
POST   /v1/screener/validate      Validate filter syntax without running
GET    /v1/screener/metrics        List all screenable metrics with metadata
GET    /v1/screener/operators      List valid operators per metric type
```

#### POST /v1/screener/run

The core endpoint — takes filters, returns matching stocks with selected columns.

```
Request:
{
  "filters": [
    { "metric": "market_cap_m", "operator": "gte", "value": 500 },
    { "metric": "pe_ratio", "operator": "lte", "value": 20 },
    { "metric": "dividend_yield_pct", "operator": "gte", "value": 3.5 },
    { "metric": "franking_pct", "operator": "eq", "value": 100 }
  ],
  "filter_logic": "AND",           // AND | OR | custom (Pro)
  "universe": {
    "index": "ASX200",             // ALL | ASX20 | ASX50 | ASX100 | ASX200 | ASX300
    "sectors": ["Financials", "Materials"],
    "types": ["bank", "miner"],    // any | bank | miner | reit | lic | etf
    "market_cap_min_m": null,
    "market_cap_max_m": null
  },
  "columns": [
    "ticker", "company_name", "sector",
    "market_cap_m", "pe_ratio", "dividend_yield_pct",
    "franking_pct", "grossed_up_yield_pct", "roe_pct"
  ],
  "sort_by": "grossed_up_yield_pct",
  "sort_order": "desc",
  "page": 1,
  "page_size": 25
}

Response 200:
{
  "data": [
    {
      "ticker": "WBC",
      "company_name": "Westpac Banking Corporation",
      "sector": "Financials",
      "market_cap_m": 92410.5,
      "pe_ratio": 11.2,
      "dividend_yield_pct": 6.8,
      "franking_pct": 100.0,
      "grossed_up_yield_pct": 9.71,
      "roe_pct": 10.4
    },
    ...
  ],
  "pagination": { ... },
  "meta": {
    "total_stocks_screened": 2200,
    "matches": 47,
    "data_as_of": "2026-04-20T16:00:00+10:00",
    "compute_time_ms": 142
  }
}

Errors:
  400 { "detail": "Unknown metric: 'pe_ratiooo'" }
  400 { "detail": "Operator 'contains' not valid for numeric metric 'pe_ratio'" }
  429 Rate limited
```

#### Implementation note (Elasticsearch-backed)

```python
# routers/screener.py

@router.post("/run", response_model=ScreenerResponse)
async def run_screener(
    body: ScreenerRequest,
    user: Optional[User] = Depends(get_optional_user),
    es: AsyncElasticsearch = Depends(get_elasticsearch),
    redis: Redis = Depends(get_redis),
):
    plan = user.plan if user else "anonymous"

    # Build Elasticsearch query from filters
    es_query = build_es_query(body.filters, body.universe, body.filter_logic)

    # Apply column restrictions for free plan
    columns = restrict_columns(body.columns, plan)

    # Check result cache (key = hash of query body)
    cache_key = f"screen:{hash_query(body)}"
    if cached := await redis.get(cache_key):
        return ScreenerResponse.parse_raw(cached)

    result = await es.search(
        index="asx_metrics",
        body=es_query,
        source=columns,
        from_=(body.page - 1) * body.page_size,
        size=body.page_size,
        sort=[{body.sort_by: {"order": body.sort_order}}],
    )

    response = build_screener_response(result, body)

    # Cache for 5 minutes
    await redis.setex(cache_key, 300, response.json())
    return response
```

---

### 4.3 Stock Endpoints

```
GET    /v1/stocks                  List/search stocks (paginated)
GET    /v1/stocks/{ticker}         Full stock overview
GET    /v1/stocks/{ticker}/price   Current price + OHLCV
GET    /v1/stocks/{ticker}/chart   Historical OHLCV for chart
GET    /v1/stocks/{ticker}/metrics All computed metrics (latest)
GET    /v1/stocks/{ticker}/metrics/history  Metric history (Pro)
GET    /v1/stocks/{ticker}/peers   Peer comparison
GET    /v1/stocks/{ticker}/dividends  Dividend history
GET    /v1/stocks/{ticker}/announcements  ASX announcements
GET    /v1/stocks/{ticker}/short-interest  ASIC short data history
GET    /v1/stocks/{ticker}/capital-raises  Capital raise history
```

#### GET /v1/stocks/{ticker}

```
Response 200:
{
  "ticker": "BHP",
  "company_name": "BHP Group Limited",
  "abn": "49 004 028 077",
  "sector": "Materials",
  "industry": "Diversified Metals & Mining",
  "description": "BHP is a diversified natural resources company...",
  "website": "https://www.bhp.com",
  "listing_date": "1885-01-01",
  "is_asx200": true,
  "is_asx300": true,
  "is_miner": true,
  "is_reit": false,
  "shares_outstanding": 5059000000,
  "employee_count": 80000,
  "price": {
    "last": 45.20,
    "change": 0.54,
    "change_pct": 1.22,
    "open": 44.80,
    "high": 45.45,
    "low": 44.65,
    "volume": 18400000,
    "vwap": 45.12,
    "as_of": "2026-04-20T16:00:00+10:00"
  },
  "key_metrics": {
    "market_cap_m": 218432.5,
    "enterprise_value_m": 231204.0,
    "pe_ratio": 12.4,
    "pb_ratio": 1.8,
    "ps_ratio": 1.9,
    "ev_ebitda": 7.2,
    "dividend_yield_pct": 5.2,
    "franking_pct": 100.0,
    "grossed_up_yield_pct": 7.43,
    "roe_pct": 18.4,
    "roa_pct": 8.2,
    "net_margin_pct": 16.8,
    "debt_equity_ratio": 0.42,
    "piotroski_score": 7,
    "altman_z_score": 3.4,
    "week_52_high": 52.30,
    "week_52_low": 36.80,
    "beta_1y": 0.82
  },
  "asx_specific": {
    "aisc_per_tonne": 1847.0,          // miners only, null otherwise
    "reserve_life_years": 33,
    "ffo_yield_pct": null,             // REITs only
    "nta_per_share": null,
    "wale_years": null,
    "short_interest_pct": 2.1,
    "next_ex_dividend_date": "2026-04-28",
    "next_results_date": "2026-08-19"
  }
}

Errors:
  404 { "detail": "Ticker 'XYZ' not found on ASX" }
```

#### GET /v1/stocks/{ticker}/chart

```
Query params:
  ?period=1y          // 1d | 5d | 1m | 3m | 6m | ytd | 1y | 3y | 5y | 10y | max
  ?interval=1d        // 1m | 5m | 15m | 1h | 1d | 1w | 1mo
  ?include_volume=true
  ?compare=XJO,BHP    // comma-sep tickers to overlay (Pro)

Response 200:
{
  "ticker": "BHP",
  "period": "1y",
  "interval": "1d",
  "currency": "AUD",
  "data": [
    {
      "date": "2025-04-22",
      "open": 38.40,
      "high": 38.90,
      "low": 38.10,
      "close": 38.75,
      "volume": 16200000,
      "adjusted_close": 38.75
    },
    ...
  ],
  "comparisons": {
    "XJO": [...]
  }
}
```

#### GET /v1/stocks/{ticker}/metrics/history  [Pro]

```
Query params:
  ?metrics=pe_ratio,roe_pct,dividend_yield_pct
  ?from=2023-01-01
  ?to=2026-04-20
  ?frequency=monthly    // daily | weekly | monthly | quarterly | yearly

Response 200:
{
  "ticker": "BHP",
  "metrics": ["pe_ratio", "roe_pct", "dividend_yield_pct"],
  "frequency": "monthly",
  "data": [
    { "date": "2026-04-01", "pe_ratio": 12.4, "roe_pct": 18.4, "dividend_yield_pct": 5.2 },
    { "date": "2026-03-01", "pe_ratio": 11.8, "roe_pct": 18.4, "dividend_yield_pct": 5.5 },
    ...
  ]
}
```

---

### 4.4 Financials Endpoints

```
GET    /v1/stocks/{ticker}/financials/pnl           Annual P&L statements
GET    /v1/stocks/{ticker}/financials/pnl/half-year Half-year P&L
GET    /v1/stocks/{ticker}/financials/balance-sheet Annual balance sheet
GET    /v1/stocks/{ticker}/financials/cashflow      Annual cash flow
GET    /v1/stocks/{ticker}/financials/ratios        Computed ratio history [Pro]
GET    /v1/stocks/{ticker}/financials/segments      Business segment breakdown [Pro]
```

#### GET /v1/stocks/{ticker}/financials/pnl

```
Query params:
  ?periods=5          // number of years (max 20 for Pro, 3 for Free)
  ?currency=AUD       // AUD | USD

Response 200:
{
  "ticker": "BHP",
  "currency": "AUD",
  "unit": "millions",
  "periods": [
    {
      "period": "FY2026",
      "period_end": "2026-06-30",
      "is_half_year": false,
      "revenue": 59124.0,
      "gross_profit": 24706.0,
      "gross_margin_pct": 41.8,
      "ebitda": 18984.0,
      "ebitda_margin_pct": 32.1,
      "ebit": 15204.0,
      "interest_expense": -1184.0,
      "pbt": 14020.0,
      "tax_expense": -4103.0,
      "net_profit": 9917.0,
      "net_margin_pct": 16.8,
      "eps_basic": 2.018,
      "dps": 1.180,
      "dps_franking_pct": 100.0,
      "dps_grossed_up": 1.686,
      "shares_on_issue_m": 5059.0
    },
    ...
  ]
}
```

---

### 4.5 Watchlist Endpoints

```
GET    /v1/watchlists              List user's watchlists
POST   /v1/watchlists              Create watchlist
GET    /v1/watchlists/{id}         Get watchlist with holdings + live prices
PUT    /v1/watchlists/{id}         Update watchlist name/description
DELETE /v1/watchlists/{id}         Delete watchlist
POST   /v1/watchlists/{id}/items   Add ticker to watchlist
DELETE /v1/watchlists/{id}/items/{ticker}  Remove ticker
PUT    /v1/watchlists/{id}/items/reorder   Reorder items
POST   /v1/watchlists/import       Import tickers from CSV
GET    /v1/watchlists/{id}/export  Export watchlist as CSV
```

#### POST /v1/watchlists

```
Request:
{
  "name": "Big 4 Banks + Dividends",
  "description": "High-yield fully franked banks",
  "is_public": false
}

Response 201:
{
  "id": "uuid",
  "name": "Big 4 Banks + Dividends",
  "description": "High-yield fully franked banks",
  "is_public": false,
  "item_count": 0,
  "created_at": "2026-04-20T10:00:00+10:00"
}
```

#### GET /v1/watchlists/{id}

```
Response 200:
{
  "id": "uuid",
  "name": "Big 4 Banks + Dividends",
  "items": [
    {
      "ticker": "CBA",
      "company_name": "Commonwealth Bank of Australia",
      "price": 118.40,
      "change_pct": -0.3,
      "market_cap_m": 201840.0,
      "pe_ratio": 18.2,
      "dividend_yield_pct": 3.8,
      "grossed_up_yield_pct": 5.43,
      "franking_pct": 100.0,
      "week_52_change_pct": 14.1,
      "added_at": "2026-03-15T09:00:00+10:00"
    },
    ...
  ],
  "summary": {
    "avg_grossed_up_yield_pct": 8.97,
    "avg_pe_ratio": 11.2,
    "avg_52w_return_pct": 9.4,
    "total_market_cap_m": 592000.0
  }
}
```

---

### 4.6 Portfolio Endpoints  [Pro]

```
GET    /v1/portfolios              List portfolios
POST   /v1/portfolios              Create portfolio
GET    /v1/portfolios/{id}         Portfolio with holdings, P&L, income
PUT    /v1/portfolios/{id}         Update portfolio
DELETE /v1/portfolios/{id}         Delete portfolio
GET    /v1/portfolios/{id}/holdings  Holdings table with live prices
POST   /v1/portfolios/{id}/trades   Add trade
PUT    /v1/portfolios/{id}/trades/{tid}  Edit trade
DELETE /v1/portfolios/{id}/trades/{tid}  Delete trade
GET    /v1/portfolios/{id}/performance  Historical performance vs benchmark
GET    /v1/portfolios/{id}/income   Income calendar (dividends + franking)
GET    /v1/portfolios/{id}/tax      FY tax summary (CGT, franking credits)
POST   /v1/portfolios/import        Import trades from CSV (CHESS/broker format)
```

#### POST /v1/portfolios/{id}/trades

```
Request:
{
  "ticker": "BHP",
  "trade_type": "BUY",          // BUY | SELL | DIVIDEND | SPLIT | SPINOFF
  "trade_date": "2024-06-15",
  "quantity": 500,
  "price_per_share": 36.40,
  "brokerage": 9.95,
  "currency": "AUD",
  "notes": "Initial position"
}

Response 201:
{
  "id": "trade-uuid",
  "ticker": "BHP",
  "trade_type": "BUY",
  "trade_date": "2024-06-15",
  "quantity": 500,
  "price_per_share": 36.40,
  "total_cost": 18209.95,
  "brokerage": 9.95,
  "current_price": 45.20,
  "current_value": 22600.0,
  "unrealised_gain": 4390.05,
  "unrealised_gain_pct": 24.11
}
```

---

### 4.7 Alert Endpoints

```
GET    /v1/alerts              List user's alerts
POST   /v1/alerts              Create alert
GET    /v1/alerts/{id}         Get alert detail
PUT    /v1/alerts/{id}         Update alert
DELETE /v1/alerts/{id}         Delete alert
POST   /v1/alerts/{id}/pause   Pause alert
POST   /v1/alerts/{id}/resume  Resume alert
POST   /v1/alerts/{id}/snooze  Snooze for N days
GET    /v1/alerts/triggered    Recent triggered alerts (last 30 days)
```

#### POST /v1/alerts

```
Request (Price Alert):
{
  "alert_type": "price",          // price | metric | screener | announcement
  "ticker": "BHP",
  "condition": {
    "metric": "price",
    "operator": "crosses_above",  // crosses_above | crosses_below | gte | lte
    "value": 45.00
  },
  "notify_via": ["email", "push"],
  "repeat_mode": "every_time",    // once | every_time | daily_max
  "active": true
}

Request (Metric Alert):
{
  "alert_type": "metric",
  "ticker": "ANZ",
  "condition": {
    "metric": "pe_ratio",
    "operator": "lte",
    "value": 11.0
  },
  "notify_via": ["email"],
  "repeat_mode": "once"
}

Request (Screener Alert — fires when new stock enters a saved screen):
{
  "alert_type": "screener",
  "saved_screen_id": "screen-uuid",
  "notify_via": ["email", "push"],
  "repeat_mode": "every_time"
}

Response 201:
{
  "id": "alert-uuid",
  "alert_type": "price",
  "ticker": "BHP",
  "condition": { ... },
  "status": "active",
  "created_at": "2026-04-20T10:00:00+10:00",
  "last_checked": null,
  "last_triggered": null
}
```

---

### 4.8 Community Screens Endpoints

```
GET    /v1/screens              Browse community screens (public)
GET    /v1/screens/{slug}       Get screen detail + filters
POST   /v1/screens/{slug}/run   Run community screen
POST   /v1/screens              Publish screen (requires saved_screen_id)
PUT    /v1/screens/{slug}        Update own screen
DELETE /v1/screens/{slug}        Delete own screen
POST   /v1/screens/{slug}/star  Star/unstar a screen
POST   /v1/screens/{slug}/clone  Clone to your saved screens
GET    /v1/screens/my           My published screens
```

#### GET /v1/screens

```
Query params:
  ?sort=trending          // trending | top_rated | newest | most_run
  ?tags=dividends,value   // filter by tags
  ?q=high franking        // search
  ?page=1&page_size=12

Response 200:
{
  "data": [
    {
      "id": "uuid",
      "slug": "high-franking-value",
      "title": "High Franking Value Screen",
      "description": "ASX200 companies with strong dividends, fully franked...",
      "author": { "username": "dividendhunter", "reputation": 1240 },
      "tags": ["dividends", "value", "franking"],
      "filter_count": 4,
      "run_count": 847,
      "star_count": 214,
      "avg_rating": 4.8,
      "last_run_match_count": 23,
      "created_at": "2025-11-15T00:00:00+10:00",
      "updated_at": "2026-03-01T00:00:00+10:00"
    },
    ...
  ],
  "pagination": { ... }
}
```

---

### 4.9 Market Data Endpoints

```
GET    /v1/market/overview         Indices + sector performance
GET    /v1/market/sectors          All sectors with today's performance
GET    /v1/market/movers/gainers   Top gainers today (ASX200)
GET    /v1/market/movers/losers    Top losers today (ASX200)
GET    /v1/market/movers/volume    Unusual volume stocks
GET    /v1/market/short-interest   ASIC short interest leaderboard
GET    /v1/market/dividends        Upcoming ex-dividend dates
GET    /v1/market/capital-raises   Active capital raises
GET    /v1/market/announcements    Latest ASX announcements feed
GET    /v1/market/calendar         Economic / results calendar
```

#### GET /v1/market/overview

```
Response 200:
{
  "as_of": "2026-04-20T16:00:00+10:00",
  "indices": [
    { "code": "XJO", "name": "S&P/ASX 200", "value": 7842.3, "change_pct": 0.42 },
    { "code": "XAO", "name": "All Ordinaries", "value": 8012.1, "change_pct": 0.51 },
    { "code": "XKO", "name": "S&P/ASX 300", "value": 7621.4, "change_pct": 0.38 }
  ],
  "sectors": [
    { "name": "Materials", "change_pct": 1.8, "advance": 42, "decline": 18 },
    { "name": "Financials", "change_pct": 0.5, "advance": 24, "decline": 12 },
    ...
  ],
  "market_stats": {
    "advancing": 1240,
    "declining": 820,
    "unchanged": 140,
    "new_52w_high": 52,
    "new_52w_low": 18
  }
}
```

#### GET /v1/market/short-interest

```
Query params:
  ?min_short_pct=5
  ?sort=short_pct_desc
  ?page=1&page_size=25

Response 200:
{
  "data_date": "2026-04-18",    // ASIC publishes with 2-day lag
  "data": [
    {
      "ticker": "GXY",
      "company_name": "Galaxy Resources",
      "short_shares": 48200000,
      "shares_outstanding": 262000000,
      "short_pct": 18.4,
      "short_pct_prev": 17.1,
      "short_pct_change": 1.3,
      "trend": "increasing",
      "price": 3.12,
      "market_cap_m": 817.0
    },
    ...
  ]
}
```

---

### 4.10 AI / Claude Endpoints  [Pro/Premium]

```
POST   /v1/ai/screener            Natural language → screener filters [Pro]
POST   /v1/ai/chat/{ticker}       Chat with annual report [Pro]
GET    /v1/ai/summary/{ticker}    AI stock summary [Pro]
POST   /v1/ai/compare             AI compare two stocks [Pro]
GET    /v1/ai/insights/feed       AI market insights feed [Premium]
POST   /v1/ai/classify            Classify announcement (internal/admin only)
```

#### POST /v1/ai/screener  [Pro]

```
Request:
{
  "prompt": "ASX200 companies with strong dividends, fully franked, low debt, consistent profit growth over 5 years"
}

Response 200:
{
  "filters": [
    { "metric": "is_asx200", "operator": "eq", "value": true },
    { "metric": "dividend_yield_pct", "operator": "gte", "value": 3.5 },
    { "metric": "franking_pct", "operator": "eq", "value": 100 },
    { "metric": "debt_equity_ratio", "operator": "lte", "value": 0.5 },
    { "metric": "revenue_cagr_5y_pct", "operator": "gte", "value": 5 },
    { "metric": "eps_cagr_5y_pct", "operator": "gte", "value": 5 }
  ],
  "explanation": "Filtered to ASX200 for blue-chip quality, dividend yield ≥3.5% to capture income stocks, 100% franking for full grossed-up yield, Debt/Equity ≤0.5 for balance sheet strength, and 5Y CAGR ≥5% for both revenue and EPS to show consistent growth.",
  "claude_model": "claude-haiku-4-5",
  "tokens_used": 312
}
```

#### POST /v1/ai/chat/{ticker}  [Pro]

Streaming response (Server-Sent Events).

```
Request:
{
  "question": "What is BHP's copper production guidance for FY27?",
  "document_filter": ["FY26_H1", "FY25_ANNUAL"]   // optional, searches all if omitted
}

Response: text/event-stream
data: {"delta": "Based"}
data: {"delta": " on BHP"}
data: {"delta": "'s FY26 half-year"}
...
data: {"delta": ".", "sources": [
  { "document": "FY26 H1 Results", "page": 24, "excerpt": "Copper production guidance of 1.84-2.04 Mt for FY27..." }
]}
data: [DONE]
```

---

### 4.11 Admin / Internal Endpoints

```
GET    /v1/internal/health              Basic health check (public)
GET    /v1/internal/ready               Readiness (DB + ES + Redis connected)
GET    /v1/internal/metrics             Prometheus metrics
POST   /v1/internal/compute/trigger     Trigger compute run for ticker(s) [admin]
POST   /v1/internal/cache/invalidate    Flush cache for ticker [admin]
GET    /v1/internal/pipeline/status     Airflow DAG status [admin]
POST   /v1/internal/announcements/classify  Re-classify announcements [admin]
```

#### GET /v1/internal/health

```
Response 200:
{
  "status": "ok",
  "version": "1.2.0",
  "environment": "production",
  "timestamp": "2026-04-20T16:05:00+10:00"
}
```

#### GET /v1/internal/ready

```
Response 200:
{
  "status": "ready",
  "checks": {
    "database": { "status": "ok", "latency_ms": 2 },
    "redis": { "status": "ok", "latency_ms": 0 },
    "elasticsearch": { "status": "ok", "latency_ms": 4 },
    "last_price_load": "2026-04-20T16:02:00+10:00",
    "last_compute_run": "2026-04-20T17:31:00+10:00"
  }
}

Response 503 (if any check fails):
{
  "status": "not_ready",
  "checks": {
    "database": { "status": "error", "error": "Connection timeout" },
    ...
  }
}
```

---

## 5. WebSocket Endpoints

```
WS     /v1/ws/prices              Live price feed for subscribed tickers
WS     /v1/ws/alerts              Real-time alert trigger notifications
```

### WS /v1/ws/prices

```python
# routers/ws.py

@router.websocket("/prices")
async def price_feed(
    websocket: WebSocket,
    token: str = Query(...),   # JWT passed as query param for WS
):
    await websocket.accept()
    user = await validate_ws_token(token)
    subscribed_tickers: set[str] = set()

    try:
        while True:
            msg = await websocket.receive_json()

            if msg["action"] == "subscribe":
                subscribed_tickers.update(msg["tickers"])

            elif msg["action"] == "unsubscribe":
                subscribed_tickers.difference_update(msg["tickers"])

            # Push price updates from Redis pub/sub
            async for ticker, price_data in redis_price_stream(subscribed_tickers):
                await websocket.send_json({
                    "type": "price_update",
                    "ticker": ticker,
                    "price": price_data["last"],
                    "change_pct": price_data["change_pct"],
                    "volume": price_data["volume"],
                    "timestamp": price_data["timestamp"]
                })

    except WebSocketDisconnect:
        pass
```

Client subscribe message:
```json
{ "action": "subscribe", "tickers": ["BHP", "CBA", "WBC"] }
```

Server push:
```json
{ "type": "price_update", "ticker": "BHP", "price": 45.20, "change_pct": 1.22, "timestamp": "..." }
```

---

## 6. Request / Response Schemas (Pydantic)

```python
# schemas/screener.py

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Literal
from enum import Enum

class FilterOperator(str, Enum):
    gte = "gte"
    lte = "lte"
    gt = "gt"
    lt = "lt"
    eq = "eq"
    neq = "neq"
    between = "between"
    in_list = "in"
    crosses_above = "crosses_above"
    crosses_below = "crosses_below"

class FilterItem(BaseModel):
    metric: str = Field(..., description="Metric key from meta.metric_definitions")
    operator: FilterOperator
    value: float | int | bool | str | list
    value2: Optional[float] = None   # for 'between' operator

    @validator("metric")
    def validate_metric(cls, v):
        if v not in VALID_METRICS:
            raise ValueError(f"Unknown metric: '{v}'")
        return v

class UniverseFilter(BaseModel):
    index: Literal["ALL", "ASX20", "ASX50", "ASX100", "ASX200", "ASX300"] = "ALL"
    sectors: List[str] = []
    types: List[str] = []
    market_cap_min_m: Optional[float] = None
    market_cap_max_m: Optional[float] = None

class ScreenerRequest(BaseModel):
    filters: List[FilterItem] = Field(..., min_items=1, max_items=50)
    filter_logic: Literal["AND", "OR"] = "AND"
    universe: UniverseFilter = UniverseFilter()
    columns: List[str] = Field(default_factory=lambda: DEFAULT_COLUMNS)
    sort_by: str = "market_cap_m"
    sort_order: Literal["asc", "desc"] = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=200)

class StockSummary(BaseModel):
    ticker: str
    company_name: str
    sector: Optional[str]
    market_cap_m: Optional[float]
    pe_ratio: Optional[float]
    dividend_yield_pct: Optional[float]
    franking_pct: Optional[float]
    grossed_up_yield_pct: Optional[float]
    # ... other selected columns as Optional[float]

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool

class ScreenerMeta(BaseModel):
    total_stocks_screened: int
    matches: int
    data_as_of: str
    compute_time_ms: int

class ScreenerResponse(BaseModel):
    data: List[dict]
    pagination: PaginationMeta
    meta: ScreenerMeta
```

```python
# schemas/stock.py

class PriceData(BaseModel):
    last: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: int
    vwap: Optional[float]
    as_of: str

class KeyMetrics(BaseModel):
    market_cap_m: Optional[float]
    enterprise_value_m: Optional[float]
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    ps_ratio: Optional[float]
    ev_ebitda: Optional[float]
    dividend_yield_pct: Optional[float]
    franking_pct: Optional[float]
    grossed_up_yield_pct: Optional[float]
    roe_pct: Optional[float]
    roa_pct: Optional[float]
    net_margin_pct: Optional[float]
    debt_equity_ratio: Optional[float]
    piotroski_score: Optional[int]
    altman_z_score: Optional[float]
    week_52_high: Optional[float]
    week_52_low: Optional[float]
    beta_1y: Optional[float]

class ASXSpecific(BaseModel):
    aisc_per_tonne: Optional[float]          # miners
    reserve_life_years: Optional[int]        # miners
    ffo_yield_pct: Optional[float]           # REITs
    nta_per_share: Optional[float]           # REITs / LICs
    wale_years: Optional[float]              # REITs
    occupancy_pct: Optional[float]           # REITs
    short_interest_pct: Optional[float]
    next_ex_dividend_date: Optional[str]
    next_results_date: Optional[str]

class StockDetail(BaseModel):
    ticker: str
    company_name: str
    abn: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    description: Optional[str]
    website: Optional[str]
    listing_date: Optional[str]
    is_asx200: bool = False
    is_asx300: bool = False
    is_miner: bool = False
    is_reit: bool = False
    shares_outstanding: Optional[int]
    employee_count: Optional[int]
    price: PriceData
    key_metrics: KeyMetrics
    asx_specific: ASXSpecific
```

---

## 7. Error Handling

### Standard Error Response

```python
# schemas/errors.py

class ErrorDetail(BaseModel):
    code: str           # machine-readable error code
    message: str        # human-readable message
    field: Optional[str] = None   # for validation errors

class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str     # from X-Request-ID header

# Example errors:
# 400 { "error": { "code": "INVALID_METRIC", "message": "Unknown metric: 'pe_ratiooo'", "field": "filters[0].metric" } }
# 401 { "error": { "code": "TOKEN_EXPIRED", "message": "Access token has expired" } }
# 403 { "error": { "code": "PLAN_REQUIRED", "message": "Pro subscription required for this feature" } }
# 404 { "error": { "code": "TICKER_NOT_FOUND", "message": "Ticker 'XYZ' not found on ASX" } }
# 429 { "error": { "code": "RATE_LIMITED", "message": "Rate limit exceeded. Try again in 13 seconds." } }
# 500 { "error": { "code": "INTERNAL_ERROR", "message": "An unexpected error occurred. Our team has been notified." } }
```

```python
# exception_handlers.py

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        errors.append({
            "code": "VALIDATION_ERROR",
            "message": err["msg"],
            "field": ".".join(str(loc) for loc in err["loc"])
        })
    return JSONResponse(
        status_code=422,
        content={"errors": errors, "request_id": request.state.request_id}
    )

@app.exception_handler(TickerNotFoundError)
async def ticker_not_found_handler(request: Request, exc: TickerNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "TICKER_NOT_FOUND", "message": str(exc)},
                 "request_id": request.state.request_id}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR",
                           "message": "An unexpected error occurred. Our team has been notified."},
                 "request_id": request.state.request_id}
    )
```

---

## 8. FastAPI Application Structure

```
backend/
├── main.py                    ← App factory, middleware, router registration
├── config.py                  ← Settings (pydantic-settings, reads .env)
├── deps/
│   ├── auth.py                ← get_current_user, require_pro, require_premium
│   ├── database.py            ← get_db (AsyncSession factory)
│   ├── redis.py               ← get_redis
│   └── elasticsearch.py       ← get_elasticsearch
├── routers/
│   ├── auth.py                ← /v1/auth/*
│   ├── screener.py            ← /v1/screener/*
│   ├── stocks.py              ← /v1/stocks/*
│   ├── watchlists.py          ← /v1/watchlists/*
│   ├── portfolio.py           ← /v1/portfolios/* [Pro]
│   ├── alerts.py              ← /v1/alerts/*
│   ├── screens.py             ← /v1/screens/*
│   ├── market.py              ← /v1/market/*
│   ├── ai.py                  ← /v1/ai/* [Pro/Premium]
│   ├── ws.py                  ← /v1/ws/* (WebSocket)
│   └── internal.py            ← /v1/internal/*
├── schemas/
│   ├── auth.py
│   ├── screener.py
│   ├── stock.py
│   ├── financials.py
│   ├── watchlist.py
│   ├── portfolio.py
│   ├── alert.py
│   ├── market.py
│   ├── ai.py
│   └── errors.py
├── models/
│   ├── user.py                ← SQLAlchemy ORM models
│   ├── watchlist.py
│   ├── portfolio.py
│   └── alert.py
├── services/
│   ├── screener_service.py    ← Business logic for screener queries
│   ├── stock_service.py       ← Fetch + cache stock data
│   ├── alert_service.py       ← Alert evaluation + notification dispatch
│   ├── ai_service.py          ← Claude API integration
│   ├── email_service.py       ← Resend (transactional email)
│   └── stripe_service.py      ← Subscription management
├── middleware/
│   ├── rate_limit.py
│   ├── logging.py
│   └── request_id.py
└── utils/
    ├── es_query_builder.py    ← Filter → Elasticsearch DSL translator
    ├── cache.py               ← Redis cache helpers
    └── security.py            ← JWT, password hashing
```

### main.py

```python
# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager

from config import settings
from routers import auth, screener, stocks, watchlists, portfolio, alerts, screens, market, ai, ws, internal
from middleware.rate_limit import RateLimitMiddleware
from middleware.logging import LoggingMiddleware
from middleware.request_id import RequestIDMiddleware
from deps.database import init_db
from deps.elasticsearch import init_elasticsearch

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await init_elasticsearch()
    yield
    # Shutdown (cleanup if needed)

app = FastAPI(
    title="ASX Screener API",
    description="Australian Stock Exchange screener with franking credits, mining & REIT depth",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Middleware (outermost → innermost)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(auth.router,       prefix="/v1/auth",       tags=["Auth"])
app.include_router(screener.router,   prefix="/v1/screener",   tags=["Screener"])
app.include_router(stocks.router,     prefix="/v1/stocks",     tags=["Stocks"])
app.include_router(watchlists.router, prefix="/v1/watchlists", tags=["Watchlists"])
app.include_router(portfolio.router,  prefix="/v1/portfolios", tags=["Portfolio"])
app.include_router(alerts.router,     prefix="/v1/alerts",     tags=["Alerts"])
app.include_router(screens.router,    prefix="/v1/screens",    tags=["Community Screens"])
app.include_router(market.router,     prefix="/v1/market",     tags=["Market Data"])
app.include_router(ai.router,         prefix="/v1/ai",         tags=["AI"])
app.include_router(ws.router,         prefix="/v1/ws",         tags=["WebSocket"])
app.include_router(internal.router,   prefix="/v1/internal",   tags=["Internal"])
```

---

## 9. Caching Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│  REDIS CACHE KEYS & TTLs                                         │
├───────────────────────────────────┬─────────────────────────────┤
│  Key Pattern                      │  TTL       │  Invalidated by │
├───────────────────────────────────┼────────────┼─────────────────┤
│  price:{ticker}                   │  60s       │  Price ingest   │
│  metrics:{ticker}                 │  300s      │  Compute engine │
│  chart:{ticker}:{period}          │  300s      │  Price ingest   │
│  screener:{query_hash}            │  300s      │  Compute engine │
│  market:overview                  │  60s       │  Price ingest   │
│  market:sectors                   │  300s      │  Price ingest   │
│  market:short_interest            │  3600s     │  ASIC ingest    │
│  stock:{ticker}:detail            │  300s      │  Compute engine │
│  stock:{ticker}:financials:{type} │  86400s    │  Financial ingest│
│  watchlist:{id}:snapshot          │  60s       │  Price ingest   │
│  community_screens:trending        │  1800s     │  Scheduled      │
│  ai:summary:{ticker}              │  86400s    │  New results    │
└───────────────────────────────────┴────────────┴─────────────────┘

Cache-aside pattern:
  1. Check Redis → hit → return
  2. Miss → query DB/ES → store in Redis → return

Cache invalidation (compute engine publishes to Redis channel):
  PUBLISH cache:invalidate {"type": "ticker", "tickers": ["BHP", "RIO"]}
  → API server subscribes, deletes affected keys
```

---

## 10. API Versioning

```
Strategy: URL path versioning (/v1/, /v2/)
Current:  v1 (stable)
Policy:
  - v1 maintained for minimum 12 months after v2 GA
  - Breaking changes → new version
  - Additive changes (new fields, new endpoints) → same version
  - Deprecated endpoints return Deprecation header

Response header for deprecated endpoints:
  Deprecation: true
  Sunset: Sat, 20 Apr 2027 00:00:00 GMT
  Link: <https://api.asxscreener.com.au/v2/stocks>; rel="successor-version"
```

---

## Summary

| Category | Endpoints | Auth Required | Notes |
|---|---|---|---|
| Auth | 10 | Varies | JWT + refresh cookie |
| Screener | 4 | Optional | Core product |
| Stocks | 10 | Optional | Price/metrics cached |
| Financials | 6 | Optional (3yr) / Pro (10yr+) | Cached 24h |
| Watchlists | 9 | Required | Per-user |
| Portfolio | 10 | Pro | Per-user |
| Alerts | 9 | Required | Redis pub/sub |
| Community Screens | 8 | Optional (read) | Cached |
| Market Data | 9 | Optional | Cached 60-300s |
| AI / Claude | 6 | Pro / Premium | Rate limited |
| WebSocket | 2 | Required | Real-time |
| Internal | 7 | Admin | Health + ops |
| **Total** | **90** | | |

---

*Next: `12_Codebase_Scaffold.md` — actual project file structure, docker-compose, .env, first runnable skeleton*
