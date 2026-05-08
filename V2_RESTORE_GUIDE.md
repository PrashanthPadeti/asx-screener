# ASX Screener — Version 2.0 Restore Guide
**Tagged:** 2026-05-09  
**Git Tag:** v2.0.0  
**Git Commit:** 51ad472  
**Server:** ubuntu-s-2vcpu-4gb-syd1 (DigitalOcean Sydney)  
**IP:** 209.38.84.102  
**Domain:** asxscreener.com.au  

---

## What Is In v2.0.0

### Features Shipped
- Full ASX stock screener with 80+ filters
- Company detail pages (financials, dividends, peers, half-yearly, technicals, AI summary)
- Market Overview: ASX 200/300 index snapshots, sector heatmap, top movers, heavy buying/selling, ex-div calendar, market signals, anomaly feed
- Screener presets + AI Natural Language screener (Pro/Premium)
- Watchlist, Portfolio (CGT, tax report, dividends), Alerts
- Data pages: Indices, ETFs/Funds, Global Markets, Commodities, News/Announcements
- Auth: register, login, email verification, forgot/reset password
- Billing: Stripe plans (Free / Pro / Premium / Enterprise)
- Admin: support ticket dashboard
- Notifications: email + SMS (Resend + Twilio)
- Anomaly detection: 7 flag types, 393 active flags across 352 stocks
- Heavy Buying / Heavy Selling (volume pressure, replaces shorted)
- All daily/weekly compute pipelines wired and tested

### Known Limitations in v2.0
- ASIC short position data unavailable (JS-rendered page, no API)
- `return_1d` not in screener.universe (removed from anomaly API)

---

## Infrastructure

### Server
| Item | Value |
|------|-------|
| Provider | DigitalOcean |
| Region | Sydney (syd1) |
| Size | 2 vCPU / 4 GB RAM |
| OS | Ubuntu 22.04 LTS |
| IP | 209.38.84.102 |
| Root login | SSH key (publickey) |

### Key Paths on Server
```
/opt/asx-screener/          # repo root
/opt/asx-screener/backend/  # FastAPI app
/opt/asx-screener/frontend/ # Next.js app
/opt/asx-screener/asx-venv/ # Python virtualenv (python 3.12)
/opt/asx-screener/start_backend.sh  # uvicorn start script
/opt/asx-screener/.env              # environment variables
/root/.pm2/                 # PM2 logs and config
```

### PM2 Processes
| ID | Name | Script |
|----|------|--------|
| 3 | asx-backend | /opt/asx-screener/start_backend.sh |
| 1 | asx-frontend | next start (in /opt/asx-screener/frontend) |

### Python Virtualenv
- Location: `/opt/asx-screener/asx-venv`
- Python: 3.12
- Activated: `source /opt/asx-screener/asx-venv/bin/activate`
- Or use directly: `/opt/asx-screener/asx-venv/bin/python`

---

## Database

### PostgreSQL
| Item | Value |
|------|-------|
| Host | localhost:5432 |
| Database | asx_screener |
| User | asx_user |
| Password | asx_secure_2024 |
| Connection | postgresql+asyncpg://asx_user:asx_secure_2024@localhost:5432/asx_screener |

### Key Schemas
| Schema | Purpose |
|--------|---------|
| screener | universe (main stock data table), companies |
| market | daily_prices, index_snapshots, sector_snapshots, mover_snapshots, exdiv_snapshots, anomalies, short_positions, period_metrics, asx_index_constituents, global_indices, global_fx_rates, commodity_prices, fund_prices, funds, indices |
| users | users, sessions, alerts, watchlists, portfolios, holdings, transactions, support_tickets |
| staging | eod_prices, short_positions |

### Take a DB Backup
```bash
pg_dump postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener \
  -Fc -f /opt/backups/asx_screener_v2_$(date +%Y%m%d).dump
```

### Restore a DB Backup
```bash
createdb -U postgres asx_screener_restore
pg_restore -U postgres -d asx_screener_restore /opt/backups/asx_screener_v2_YYYYMMDD.dump
```

---

## Environment Variables

### Backend (.env at /opt/asx-screener/.env or set in start_backend.sh)
```bash
DATABASE_URL=postgresql+asyncpg://asx_user:asx_secure_2024@localhost:5432/asx_screener
DATABASE_URL_SYNC=postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener
JWT_SECRET=<from server>
ENVIRONMENT=production
DEBUG=False
EODHD_API_KEY=<from server>
ANTHROPIC_API_KEY=<from server>
STRIPE_SECRET_KEY=<from server>
STRIPE_WEBHOOK_SECRET=<from server>
RESEND_API_KEY=<from server>
EMAIL_FROM=noreply@asxscreener.com.au
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://209.38.84.102:8000
```
> For production with Cloudflare proxy, this should point to https://api.asxscreener.com.au or the proxied backend URL.

---

## Cloudflare

### DNS Records (asxscreener.com.au)
| Type | Name | Value | Proxied |
|------|------|-------|---------|
| A | @ | 209.38.84.102 | Yes (orange cloud) |
| A | www | 209.38.84.102 | Yes |
| CNAME | api | 209.38.84.102 | Check |

### Settings
- SSL/TLS: Full (strict) or Flexible depending on server cert setup
- Always HTTPS: On
- Bot Fight Mode: Check current setting

---

## How to Restore to v2.0.0 from Scratch

### Step 1 — Provision Server
```bash
# DigitalOcean: create Ubuntu 22.04 droplet, 2 vCPU / 4GB, Sydney region
# Add SSH key, get IP
```

### Step 2 — Install Dependencies
```bash
apt update && apt upgrade -y
apt install -y git python3.12 python3.12-venv python3-pip postgresql postgresql-client nodejs npm nginx

# Install PM2
npm install -g pm2

# Install Node 20+ (if needed)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
```

### Step 3 — Clone Repo at v2.0.0
```bash
cd /opt
git clone https://github.com/PrashanthPadeti/asx-screener.git
cd asx-screener
git checkout v2.0.0
```

### Step 4 — Python Virtualenv
```bash
cd /opt/asx-screener
python3.12 -m venv asx-venv
source asx-venv/bin/activate
pip install -r backend/requirements.txt
```

### Step 5 — PostgreSQL Setup
```bash
sudo -u postgres psql -c "CREATE USER asx_user WITH PASSWORD 'asx_secure_2024';"
sudo -u postgres psql -c "CREATE DATABASE asx_screener OWNER asx_user;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE asx_screener TO asx_user;"
```

### Step 6 — Restore Database from Backup
```bash
pg_restore -U postgres -d asx_screener /opt/backups/asx_screener_v2_YYYYMMDD.dump
```

### Step 7 — Set Environment Variables
```bash
# Create /opt/asx-screener/.env with all values from the Environment Variables section above
# Or set them in start_backend.sh
```

### Step 8 — Build Frontend
```bash
cd /opt/asx-screener/frontend
npm install
npm run build
```

### Step 9 — Start Services with PM2
```bash
# Backend
pm2 start /opt/asx-screener/start_backend.sh --name asx-backend

# Frontend
cd /opt/asx-screener/frontend
pm2 start npm --name asx-frontend -- start

pm2 save
pm2 startup  # follow instructions to enable on reboot
```

### Step 10 — Re-run Initial Compute Jobs
```bash
export DATABASE_URL="postgresql+asyncpg://asx_user:asx_secure_2024@localhost:5432/asx_screener"
cd /opt/asx-screener/backend

# ASX index flags
/opt/asx-screener/asx-venv/bin/python -m compute.engine.asx_indices

# Market snapshot
/opt/asx-screener/asx-venv/bin/python -m compute.engine.market_snapshot

# Anomaly detection
/opt/asx-screener/asx-venv/bin/python -m compute.engine.anomaly_detect
```

### Step 11 — Update Cloudflare DNS
- Point A record @ and www to new server IP
- Wait for propagation (~5 min with Cloudflare)

---

## Daily Scheduler (APScheduler — runs inside FastAPI)

| Time AEST | Job | Description |
|-----------|-----|-------------|
| Every 10 min | fetch_announcements | ASX filings from EODHD |
| Every 15 min | check_alerts | Price/pct alerts → email/SMS |
| Every 30 min | check_portfolio_thresholds | Portfolio alerts |
| 7:30am | send_watchlist_digests | Daily watchlist email |
| Mon 8:00am | send_weekly_portfolio_summaries | Weekly portfolio email |
| 5:30pm | compute_index_prices | ASX index OHLCV |
| 5:35pm | compute_fund_prices | ETF/fund prices |
| 5:40pm | compute_global_markets | Global indices + AUD FX |
| 5:45pm | compute_commodities | Gold, oil, copper etc. |
| 5:50pm | run_asx_indices | ASX 200/300 flags |
| 6:30pm | run_short_positions | ASIC short data (empty — JS-rendered) |
| 6:45pm | run_market_snapshot | Movers, sectors, ex-div |
| 7:00pm | run_anomaly_detect | 7 anomaly flag types |

## Universe Build Pipeline (system cron — separate)

| Schedule | Script | Description |
|----------|--------|-------------|
| Weekdays 6:30pm AEST | daily_pipeline.py | EOD prices → metrics → screener.universe |
| Sunday 10pm AEST | weekly_refresh.py | Download fundamentals + dividends |
| Monday 7am AEST | weekly_pipeline.py | Load fundamentals → full universe rebuild |
| 1st Monday monthly | monthly_pipeline.py | Monthly metrics computation |

---

## Git Repository

- **URL:** https://github.com/PrashanthPadeti/asx-screener.git
- **Branch:** main
- **v2.0.0 tag:** `git checkout v2.0.0`
- **Latest commit at tag:** 51ad472

---

## Quick Health Check After Restore

```bash
# Backend health
curl http://localhost:8000/health

# Check PM2
pm2 list

# Check DB row counts
psql postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener -c "
  SELECT 'universe' AS t, COUNT(*) FROM screener.universe
  UNION ALL SELECT 'anomalies', COUNT(*) FROM market.anomalies WHERE is_active
  UNION ALL SELECT 'index_snapshots', COUNT(*) FROM market.index_snapshots
  UNION ALL SELECT 'mover_snapshots', COUNT(*) FROM market.mover_snapshots;"

# Check frontend
curl -s http://localhost:3000 | head -5
```

Expected results:
- universe: ~2000+ stocks
- anomalies: 393 active flags
- index_snapshots: 2 (ASX200 + ASX300)
- mover_snapshots: 50 (5 types × 10 rows)
