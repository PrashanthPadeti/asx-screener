# User Portal & Role-Based Access Control (RBAC)

**Version:** 1.0  
**Date:** 2026-04-28  
**Status:** Design — to be implemented after core screener is complete  

---

## Overview

Once the core ASX Screener platform is complete, a user portal will be added with
role-based access control (RBAC) to support two tiers: **Free** and **Paid/Subscribed**.
The portal should be designed so that future tiers (e.g. Professional, Enterprise) and
new feature flags (e.g. AI Recommendations) can be added without schema changes.

---

## 1. User Roles

| Role | Subscription | Description |
|------|-------------|-------------|
| `free` | None / unverified | Default on signup. Limited data and screen count. |
| `paid` | Active subscription | Full platform access. |
| `admin` | Internal | Platform management — no restrictions. |

> Future roles such as `pro` or `enterprise` slot in between `paid` and `admin`.

---

## 2. Access Matrix

### 2.1 Golden Record Data (screener.universe)

| Feature | Free | Paid |
|---------|------|------|
| Column access | Limited subset (~100 columns, TBD) | All columns |
| Row access | All stocks visible | All stocks visible |
| Export | No | Yes |

**Note:** The exact 100 columns visible to free users will be decided in a later phase.
The API layer enforces the column whitelist — free users never see the restricted columns
in any API response, regardless of what they request.

### 2.2 Stock Screening

| Feature | Free | Paid |
|---------|------|------|
| Run screens | Yes | Yes |
| Save screens | Max 10 | Unlimited |
| Share screens | No | Yes (future) |
| Custom screening queries | Limited (basic filters only) | Full query builder |
| Screener results — column visibility | Free columns only | All columns |

### 2.3 Watchlists

| Feature | Free | Paid |
|---------|------|------|
| Create watchlists | No | Yes |
| Number of watchlists | — | Unlimited (or configurable limit) |
| Stocks per watchlist | — | Unlimited |
| Watchlist alerts | — | Future phase |

### 2.4 Advanced Features

| Feature | Free | Paid |
|---------|------|------|
| Technical indicators | No | Yes |
| Company announcements (ASX) | No | Yes |
| Advanced stock analysis | No | Yes |
| AI Recommendations | No (future) | Yes (future) |
| Portfolio tracking | No (future) | Yes (future) |

---

## 3. Database Schema (Planned)

### 3.1 users table

```sql
CREATE TABLE auth.users (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255)    UNIQUE NOT NULL,
    email_verified  BOOLEAN         DEFAULT FALSE,
    password_hash   TEXT,                           -- NULL if SSO-only
    role            VARCHAR(20)     NOT NULL DEFAULT 'free',   -- free | paid | admin
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);
```

### 3.2 subscriptions table

```sql
CREATE TABLE auth.subscriptions (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            NOT NULL REFERENCES auth.users(id),
    plan                VARCHAR(50)     NOT NULL,           -- 'monthly' | 'annual'
    status              VARCHAR(20)     NOT NULL,           -- active | cancelled | past_due
    stripe_customer_id  TEXT,
    stripe_sub_id       TEXT,
    current_period_start TIMESTAMPTZ,
    current_period_end   TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);
```

### 3.3 saved_screens table

```sql
CREATE TABLE user_data.saved_screens (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID            NOT NULL REFERENCES auth.users(id),
    name        VARCHAR(100)    NOT NULL,
    description TEXT,
    filters     JSONB           NOT NULL DEFAULT '{}',   -- screener filter config
    columns     JSONB,                                   -- selected columns
    sort_by     VARCHAR(50),
    sort_dir    VARCHAR(4)      DEFAULT 'desc',
    is_public   BOOLEAN         DEFAULT FALSE,
    created_at  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     DEFAULT NOW()
);

-- Enforce free user limit at application layer (check count before insert)
CREATE INDEX idx_saved_screens_user ON user_data.saved_screens (user_id);
```

### 3.4 watchlists table

```sql
CREATE TABLE user_data.watchlists (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID            NOT NULL REFERENCES auth.users(id),
    name        VARCHAR(100)    NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     DEFAULT NOW()
);

CREATE TABLE user_data.watchlist_stocks (
    watchlist_id    UUID        NOT NULL REFERENCES user_data.watchlists(id) ON DELETE CASCADE,
    asx_code        VARCHAR(10) NOT NULL,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    notes           TEXT,
    PRIMARY KEY (watchlist_id, asx_code)
);
```

---

## 4. API Enforcement Pattern

Role checks happen in FastAPI **dependencies**, not in individual route handlers.
This keeps enforcement centralised and auditable.

```python
# Example pattern (not final code)

async def require_paid(current_user = Depends(get_current_user)):
    if current_user.role not in ("paid", "admin"):
        raise HTTPException(403, "Paid subscription required")
    return current_user

async def screener_columns(current_user = Depends(get_current_user)) -> list[str]:
    """Returns the column whitelist for the current user's role."""
    if current_user.role in ("paid", "admin"):
        return ALL_COLUMNS          # all screener.universe columns
    return FREE_COLUMNS             # ~100 approved free columns (TBD)

# Route using dependency
@router.get("/screener")
async def run_screener(
    filters: ScreenerFilters,
    columns = Depends(screener_columns),
    user    = Depends(get_current_user),
):
    results = await db.run_screener(filters, columns)
    return results
```

**Free column whitelist** (`FREE_COLUMNS`) will be defined as a config constant
once the final ~100 columns are decided. No schema changes needed — just update
the constant.

---

## 5. Saved Screen Limit Enforcement

Free users are limited to 10 saved screens. Enforced at the API layer:

```python
async def check_screen_limit(user = Depends(get_current_user), db = Depends(get_db)):
    if user.role == "free":
        count = await db.count_saved_screens(user.id)
        if count >= 10:
            raise HTTPException(403,
                "Free plan limit: 10 saved screens. Upgrade to save more.")
```

Paid users: no check (or configurable high limit like 1000).

---

## 6. Stripe Integration (Payments)

- Stripe handles payment processing and subscription lifecycle.
- Webhook events (`customer.subscription.updated`, `customer.subscription.deleted`, etc.)
  → update `auth.subscriptions` status → update `auth.users.role`.
- If subscription lapses → role reverts to `free` automatically.
- `stripe_customer_id` and `stripe_sub_id` stored in `auth.subscriptions`.

Payment UI and Stripe SDK integration to be designed in a future phase.
`stripe==11.3.0` is already in `backend/requirements.txt`.

---

## 7. Future-Proofing for AI Recommendations

When the AI Recommendations feature is added:
- No schema change needed — it's a new API endpoint gated behind `require_paid`.
- `auth.users.role` can be extended to `pro` if a separate recommendations tier is needed.
- Feature flags table (optional) can enable/disable per-user without role changes:

```sql
CREATE TABLE auth.feature_flags (
    user_id     UUID        REFERENCES auth.users(id),
    feature     VARCHAR(50),
    enabled     BOOLEAN     DEFAULT FALSE,
    PRIMARY KEY (user_id, feature)
);
```

---

## 8. Implementation Sequence (Post-Core)

1. **Auth schemas** — Create `auth` and `user_data` DB schemas + tables (new migration)
2. **JWT auth** — FastAPI JWT middleware (`python-jose` already in requirements)
3. **User registration/login endpoints** — `/auth/register`, `/auth/login`, `/auth/me`
4. **Role dependency** — `get_current_user`, `require_paid` FastAPI dependencies
5. **Column whitelist** — Define `FREE_COLUMNS` once the 100-column list is finalised
6. **Saved screens endpoints** — CRUD with free-tier limit check
7. **Watchlist endpoints** — CRUD (paid only)
8. **Stripe webhook** — Subscription lifecycle → role sync
9. **Frontend portal** — Login/signup pages, subscription upgrade CTA, account page
10. **Announcement access** — ASX announcement feed (paid only, future data source)
