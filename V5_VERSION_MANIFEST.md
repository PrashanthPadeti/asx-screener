# ASX Screener — V5.0.0 Version Manifest

**Version:** 5.0.0  
**Tag:** `v5.0.0`  
**Manifest created:** 2026-05-24  
**Git commit:** `353f60e` (HEAD at manifest creation)  
**Branch:** `main`  
**Status:** ✅ Production — Commercial Launch Ready  

---

## 1. What Is V5

V5 is the **commercial launch milestone** of ASX Screener. All core product features are live, legal pages are published, the subscription system is wired, and the platform is ready to charge real users. Prior versions (V1–V4) covered infrastructure build-out, data pipelines, screener engine, and UX polish. V5 closes the commercial gap.

---

## 2. Included Code Areas

### Frontend (`frontend/`)
| Area | Pages / Components | Status |
|------|--------------------|--------|
| Home landing | `app/page.tsx` | ✅ |
| Authentication | login, register, forgot-password, reset-password, verify-email | ✅ |
| Stock Screener | `app/screener/page.tsx` + AI query + presets | ✅ |
| Company detail | `app/company/[code]/page.tsx` | ✅ |
| Market overview | `app/market/page.tsx` | ✅ |
| Watchlist | `app/watchlist/page.tsx` | ✅ |
| Portfolio | `app/portfolio/page.tsx` | ✅ |
| Alerts | `app/alerts/page.tsx` | ✅ |
| News | `app/news/page.tsx` | ✅ |
| Scans | `app/scans/page.tsx` | ✅ |
| Top 5 strategy | `app/top5/page.tsx` | ✅ |
| Indices & Funds | `app/indices/`, `app/funds/` | ✅ |
| Global markets | `app/global-markets/` | ✅ |
| Commodities | `app/commodities/` | ✅ |
| Education hub | `app/learn/` + 3 SEO articles | ✅ V5 |
| Broker compare | `app/brokers/page.tsx` | ✅ V5 |
| Metrics glossary | `app/glossary/page.tsx` | ✅ V5 |
| Pricing | `app/pricing/page.tsx` (ToS note) | ✅ V5 |
| Contact support | `app/contact/page.tsx` | ✅ V5 |
| Privacy Policy | `app/privacy/page.tsx` | ✅ V5 NEW |
| Terms of Service | `app/terms/page.tsx` | ✅ V5 NEW |
| Account | `app/account/page.tsx` | ✅ |
| Notifications | `app/notifications/page.tsx` | ✅ |
| Admin dashboard | `app/admin/` (dashboard, pipeline, support, users, comms) | ✅ |
| Navbar | `components/Navbar.tsx` | ✅ V5 |
| Footer | `components/Footer.tsx` (legal links added) | ✅ V5 |
| PlanGate | `components/PlanGate.tsx` | ✅ |
| ClientGuard | `components/ClientGuard.tsx` | ✅ |
| HelpDrawer | `components/HelpDrawer.tsx` | ✅ |
| SearchBar | `components/SearchBar.tsx` | ✅ |
| WatchlistButton | `components/WatchlistButton.tsx` | ✅ |

### Backend (`backend/`)
| Area | Module | Status |
|------|--------|--------|
| Authentication & JWT | `routes/auth.py`, `core/security.py` | ✅ |
| Screener engine | `routes/screener.py` | ✅ |
| Company data | `routes/companies.py` | ✅ |
| Market data | `routes/market.py` | ✅ |
| Watchlist | `routes/watchlist.py` | ✅ |
| Portfolio | `routes/portfolio.py` | ✅ |
| Alerts | `routes/alerts.py` | ✅ |
| AI features | `routes/ai.py` | ✅ |
| Stripe / billing | `routes/stripe_routes.py` | ✅ |
| Support tickets | `routes/support.py` | ✅ V5 |
| Indices & funds | `routes/indices_funds.py` | ✅ |
| Global markets | `routes/global_markets.py` | ✅ |
| Commodities | `routes/commodities.py` | ✅ |
| Announcements | `routes/announcements.py` | ✅ |
| Saved screens | `routes/saved_screens.py` | ✅ |
| Admin | `routes/admin.py` | ✅ |
| Top 5 strategy | `routes/top5.py` | ✅ |
| Notifications | `routes/notifications.py` | ✅ |
| Subscription plans | `core/plans.py` | ✅ |
| Email service | `services/email.py` | ✅ V5 |
| SMS service | `services/sms.py` | ✅ |
| Notification service | `services/notification_service.py` | ✅ |
| Config (all settings) | `core/config.py` | ✅ |
| DB session | `db/session.py` | ✅ |
| Pydantic schemas | `schemas/` (8 schemas) | ✅ |

### Compute Engines (`backend/compute/engine/`)
| Engine | Purpose | Status |
|--------|---------|--------|
| daily_compute.py | Daily price + metric refresh | ✅ |
| weekly_compute.py | Weekly trend signals | ✅ |
| monthly_compute.py | Monthly aggregates | ✅ |
| quarterly_compute.py | Quarterly financials | ✅ |
| halfyearly_compute.py | Half-year results | ✅ |
| technical_compute.py | Technical indicators | ✅ |
| composite_score.py | Multi-metric ranking | ✅ |
| sector_benchmarks.py | Sector comparison | ✅ |
| mining_metrics.py | Mining-specific metrics | ✅ |
| reit_metrics.py | REIT-specific metrics | ✅ |
| pros_cons.py | Investment case generation | ✅ |
| capital_raise_tracker.py | IPO / placement tracker | ✅ |
| short_positions.py | ASIC short data | ✅ |
| top5_strategy.py | Top 5 trend following | ✅ |
| anomaly_detect.py | Price/volume anomaly | ✅ |
| + 10 more | Various metric computations | ✅ |

### Background Workers (`backend/app/workers/`)
18 workers covering: alerts, announcements, anomalies, ASX companies, indices, capital raises, cleanup, commodities, funds, global markets, market snapshots, mining/REITs, portfolio, short positions, Top 5, watchlist digests. All ✅.

### Data Ingestion Scripts (`backend/scripts/`)
40+ ETL scripts covering EODHD (primary), ASIC short positions, ASX announcements, with transforms, staging loaders, and scheduled job runners. All ✅.

---

## 3. Included Database & Schema Assets

| Asset | Location | Count | Status |
|-------|----------|-------|--------|
| SQL Migrations | `database/migrations/` | 60 files | ✅ |
| Post-launch migrations | `backend/migrations/` | 2 files | ✅ |
| Migration runner | `database/migrate.sh` | 1 script | ✅ |
| Database schemas covered | market, users, compute, screener, staging, support, ai, announcements, notifications, portfolio | 10+ schemas | ✅ |
| TimescaleDB extensions | migration 001 | ✅ |
| Seed / reference data | Built into migrations | ✅ |

**Database tech:** PostgreSQL 16 + TimescaleDB, asyncpg, SQLAlchemy 2.0 async  
**Notes:** No Alembic auto-migrations — all schema changes are explicit numbered SQL files.

---

## 4. Included Legal, Compliance & Privacy Assets

| Document | Location | Status |
|----------|----------|--------|
| Privacy Policy | `frontend/app/privacy/page.tsx` + `/privacy` | ✅ V5 NEW — Live |
| Terms of Service | `frontend/app/terms/page.tsx` + `/terms` | ✅ V5 NEW — Live |
| Financial disclaimer | Footer (every page), all learn/glossary pages | ✅ |
| Not-financial-advice wording | Terms Section 3 (highlighted), screener AI results, footer | ✅ |
| Affiliate disclosure | Terms Section 10, brokers page | ✅ |
| Data accuracy disclaimer | Terms Section 9, company pages | ✅ |
| AFSL position statement | Terms Section 3 explicitly states no AFSL held | ✅ |
| ACL rights preservation | Terms Section 12 | ✅ |
| OAIC complaints reference | Privacy Section 7 | ✅ |
| Legal & compliance design doc | `Design/12_Legal_and_Compliance.md` | ✅ |
| ToS acceptance on pricing | Pricing page — pre-checkout note | ✅ V5 |

---

## 5. Included Settings & Configurations

| Config | Location | Secrets in repo? |
|--------|----------|-----------------|
| Backend env template | `.env.example` | ❌ Placeholders only |
| Backend env (live) | Server `.env` (not in repo) | N/A — server only |
| Frontend env (live) | `frontend/.env.local` — API URL only | ❌ No secrets |
| Docker compose | `docker-compose.yml` | ❌ Refs .env only |
| Next.js config | `frontend/next.config.ts` | ❌ |
| TypeScript config | `frontend/tsconfig.json` | ❌ |
| PostCSS / Tailwind | `frontend/postcss.config.mjs` | ❌ |
| ESLint | `frontend/eslint.config.mjs` | ❌ |
| npm lockfile | `frontend/package-lock.json` | ❌ |
| Python deps | `backend/requirements.txt` | ❌ |
| Subscription tiers | `backend/app/core/plans.py` | ❌ |
| Rate limits | `backend/app/core/config.py` | ❌ |
| CORS settings | `backend/app/main.py` | ❌ |
| JWT settings | `backend/app/core/config.py` | ❌ |
| Feature flags | Via `PlanGate` component + plan checks | ❌ |
| Cron setup | `backend/scripts/eodhd/v2/jobs/setup_cron.sh` | ❌ |

**Secret keys defined (all via env — never hardcoded):**
DATABASE_URL, JWT_SECRET, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
ANTHROPIC_API_KEY, OPENAI_API_KEY, RESEND_API_KEY, EODHD_API_KEY,
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

---

## 6. Included Pipelines & Automation

| Pipeline | Location | Schedule | Status |
|----------|----------|---------|--------|
| Daily data pipeline | `scripts/eodhd/v2/jobs/daily_pipeline.py` | Daily | ✅ |
| Weekly data pipeline | `scripts/eodhd/v2/jobs/weekly_pipeline.py` | Weekly | ✅ |
| Monthly data pipeline | `scripts/eodhd/v2/jobs/monthly_pipeline.py` | Monthly | ✅ |
| Cron setup script | `scripts/eodhd/v2/jobs/setup_cron.sh` | One-time setup | ✅ |
| Pipeline runner | `scripts/eodhd/v2/jobs/pipeline_runner.py` | On-demand | ✅ |
| Deploy script | `deploy.sh` | On-demand | ✅ |
| Restore script | `restore_v5.sh` | On-demand | ✅ V5 NEW |
| DB migration runner | `database/migrate.sh` | On-demand | ✅ |
| Background workers | `backend/app/workers/` (18 workers) | APScheduler | ✅ |
| CI/CD pipeline | `.github/workflows/ci.yml` | On push | ✅ |
| Airflow orchestration | `docker-compose.yml` (Airflow 2.9) | Dev only | ✅ |

---

## 7. Backup Status

| Backup | Location | Format | Contains |
|--------|----------|--------|---------|
| **V5 local backup** | `C:\Users\Dell\My Claude\Code\ASX Screener\ASX_Screener_v5.0.0_git_2026-05-24.zip` | ZIP | Full codebase |
| **V5 server backup** | `/opt/backups/ASX_Screener_v5.0.0_backup.zip` (server) | ZIP | Full codebase |
| **V5 git tag** | `v5.0.0` on GitHub | Git annotated tag | Full history |
| **Database backup** | Server PostgreSQL pg_dump (scheduled) | SQL dump | All schemas + data |
| Prior versions | v1.0-base, v2.0.0, v3.0.0, v3.1.0, v4.0.0 on GitHub | Git tags | Code only |

---

## 8. Recovery Instructions

**Quick restore (preferred):**
```bash
cd /opt/asx-screener
git fetch --tags
./restore_v5.sh --check   # dry run
./restore_v5.sh           # actual restore
```

**Manual restore:**
```bash
cd /opt/asx-screener
git fetch --tags
git checkout v5.0.0
sudo systemctl restart asx-api
cd frontend && npm ci && npm run build
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public
pm2 restart asx-frontend
```

**Full restore guide:** See `RESTORE_v5.md` in project root.

---

## 9. Known Gaps & Exclusions

| Item | Status | Notes |
|------|--------|-------|
| Database data itself | ❌ Not in git | Use pg_dump for data backup — code repo only stores schema |
| `.env` files (live secrets) | ❌ Not in git | By design — store securely in DigitalOcean, password manager |
| `frontend/.env.local` | ⚠️ Not in git | Contains API URL — recreate from `.env.example` |
| `ASX_Screener_*.docx` files | ⚠️ Not in git | Reference docs — store in Google Drive / OneDrive |
| `generate_metrics_gap_analysis.py` | ⚠️ Not in git | Utility script — add to git or keep as local tool |
| Docs 100–103 | ❌ Not found | No files with this numbering exist — may be a future doc series |
| Airflow DAGs | ⚠️ None found | Airflow is in docker-compose but no DAG files committed — pipelines use APScheduler instead |
| Elasticsearch index mappings | ⚠️ Not found | If using ES for screener search, ensure mappings are version-controlled |
| Server `.env` backup | ⚠️ Server only | Back up manually to a secure password manager |

---

## 10. Version History

| Version | Date | Milestone |
|---------|------|-----------|
| v1.0-base | Early 2026 | Initial foundation & repo setup |
| v2.0.0 | 2026 | Core screener, company pages, DB schema |
| v3.0.0 | 2026 | Data pipelines, compute engines, auth |
| v3.1.0 | 2026-05-21 | Incremental improvements |
| v4.0.0 | 2026 | Premium features, AI screener, subscriptions |
| **v5.0.0** | **2026-05-24** | **Commercial launch ready** |

---

## 11. Post-V5 Recommended Actions

| Priority | Action |
|----------|--------|
| 🔴 High | Back up server `.env` to a secure password manager |
| 🔴 High | Set up automated pg_dump for daily database backups |
| 🔴 High | Confirm EODHD data licence covers commercial redistribution |
| 🟡 Medium | Lawyer review of Terms Section 3 (AFSL position) |
| 🟡 Medium | Register for GST if approaching $75k AUD revenue |
| 🟡 Medium | Replace `asxscreener@gmail.com` with a business email domain |
| 🟡 Medium | Add `frontend/.env.local` to backup procedure |
| 🟢 Low | Add `generate_metrics_gap_analysis.py` to git |
| 🟢 Low | Commit `.docx` reference documents or store in Google Drive |
| 🟢 Low | Enable Stripe live mode (currently confirm test/live mode) |
| 🟢 Low | Add Terms/Privacy links to the Register page (pre-signup) |
