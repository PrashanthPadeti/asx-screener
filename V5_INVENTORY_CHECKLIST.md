# ASX Screener — V5 Complete Inventory Checklist

**Audit date:** 2026-05-24  
**Auditor:** Claude (automated + manual review)  
**Git tag:** v5.0.0 | **Commit:** 353f60e  

Legend: ✅ Backed up & versioned | ⚠️ Partial / needs action | ❌ Missing / not versioned

---

## A. CODE

### A1. Frontend Code

| Asset | File Path | In Git | Backed Up | Notes |
|-------|-----------|--------|-----------|-------|
| Home page | `frontend/app/page.tsx` | ✅ | ✅ | |
| Auth — login | `frontend/app/auth/login/page.tsx` | ✅ | ✅ | |
| Auth — register | `frontend/app/auth/register/page.tsx` | ✅ | ✅ | |
| Auth — forgot password | `frontend/app/auth/forgot-password/page.tsx` | ✅ | ✅ | |
| Auth — reset password | `frontend/app/auth/reset-password/page.tsx` | ✅ | ✅ | |
| Auth — verify email | `frontend/app/auth/verify-email/page.tsx` | ✅ | ✅ | |
| Stock screener | `frontend/app/screener/page.tsx` | ✅ | ✅ | AI disclaimer added V5 |
| Company detail | `frontend/app/company/[code]/page.tsx` | ✅ | ✅ | |
| Market overview | `frontend/app/market/page.tsx` | ✅ | ✅ | |
| Watchlist | `frontend/app/watchlist/page.tsx` | ✅ | ✅ | |
| Portfolio | `frontend/app/portfolio/page.tsx` | ✅ | ✅ | |
| Alerts | `frontend/app/alerts/page.tsx` | ✅ | ✅ | |
| News | `frontend/app/news/page.tsx` | ✅ | ✅ | |
| Scans | `frontend/app/scans/page.tsx` | ✅ | ✅ | |
| Top 5 strategy | `frontend/app/top5/page.tsx` | ✅ | ✅ | |
| Indices | `frontend/app/indices/page.tsx` + `[code]` | ✅ | ✅ | |
| Funds | `frontend/app/funds/page.tsx` + `[code]` | ✅ | ✅ | |
| Global markets | `frontend/app/global-markets/page.tsx` + `[code]` | ✅ | ✅ | |
| Commodities | `frontend/app/commodities/page.tsx` + `[code]` | ✅ | ✅ | |
| Education hub | `frontend/app/learn/page.tsx` | ✅ | ✅ | Overhauled V5 |
| Learn — franking credits | `frontend/app/learn/franking-credits-explained/page.tsx` | ✅ | ✅ | New V5 |
| Learn — ratios | `frontend/app/learn/key-financial-ratios/page.tsx` | ✅ | ✅ | New V5 |
| Learn — announcements | `frontend/app/learn/how-to-read-company-announcements/page.tsx` | ✅ | ✅ | New V5 |
| Broker compare | `frontend/app/brokers/page.tsx` | ✅ | ✅ | Overhauled V5 |
| Metrics glossary | `frontend/app/glossary/page.tsx` | ✅ | ✅ | Overhauled V5 |
| Pricing | `frontend/app/pricing/page.tsx` | ✅ | ✅ | ToS note added V5 |
| Contact support | `frontend/app/contact/page.tsx` | ✅ | ✅ | Overhauled V5 |
| **Privacy Policy** | `frontend/app/privacy/page.tsx` | ✅ | ✅ | **NEW V5** |
| **Terms of Service** | `frontend/app/terms/page.tsx` | ✅ | ✅ | **NEW V5** |
| Account | `frontend/app/account/page.tsx` | ✅ | ✅ | |
| Notifications | `frontend/app/notifications/page.tsx` | ✅ | ✅ | |
| Admin dashboard | `frontend/app/admin/page.tsx` | ✅ | ✅ | |
| Admin — pipeline | `frontend/app/admin/pipeline/page.tsx` | ✅ | ✅ | |
| Admin — support | `frontend/app/admin/support/page.tsx` | ✅ | ✅ | Categories updated V5 |
| Admin — users | `frontend/app/admin/users/page.tsx` + `[id]` | ✅ | ✅ | |
| Admin — comms | `frontend/app/admin/comms/page.tsx` | ✅ | ✅ | |
| Navbar | `frontend/components/Navbar.tsx` | ✅ | ✅ | Sub-path active state fixed V5 |
| Footer | `frontend/components/Footer.tsx` | ✅ | ✅ | Legal links added V5 |
| PlanGate | `frontend/components/PlanGate.tsx` | ✅ | ✅ | |
| ClientGuard | `frontend/components/ClientGuard.tsx` | ✅ | ✅ | |
| HelpDrawer | `frontend/components/HelpDrawer.tsx` | ✅ | ✅ | |
| SearchBar | `frontend/components/SearchBar.tsx` | ✅ | ✅ | |
| WatchlistButton | `frontend/components/WatchlistButton.tsx` | ✅ | ✅ | |
| Lib / API client | `frontend/lib/api.ts` | ✅ | ✅ | |
| Lib / Auth | `frontend/lib/auth.ts` | ✅ | ✅ | |
| Lib / Utils | `frontend/lib/utils.ts` | ✅ | ✅ | |

### A2. Backend Code

| Asset | File Path | In Git | Backed Up | Notes |
|-------|-----------|--------|-----------|-------|
| FastAPI entry point | `backend/app/main.py` | ✅ | ✅ | |
| API router (v1) | `backend/app/api/v1/router.py` | ✅ | ✅ | 18 route groups |
| Auth route | `backend/app/api/v1/routes/auth.py` | ✅ | ✅ | |
| Screener route | `backend/app/api/v1/routes/screener.py` | ✅ | ✅ | |
| Companies route | `backend/app/api/v1/routes/companies.py` | ✅ | ✅ | |
| Market route | `backend/app/api/v1/routes/market.py` | ✅ | ✅ | |
| Watchlist route | `backend/app/api/v1/routes/watchlist.py` | ✅ | ✅ | |
| Portfolio route | `backend/app/api/v1/routes/portfolio.py` | ✅ | ✅ | |
| Alerts route | `backend/app/api/v1/routes/alerts.py` | ✅ | ✅ | |
| AI route | `backend/app/api/v1/routes/ai.py` | ✅ | ✅ | |
| Stripe route | `backend/app/api/v1/routes/stripe_routes.py` | ✅ | ✅ | |
| Support route | `backend/app/api/v1/routes/support.py` | ✅ | ✅ | Context tracking added V5 |
| Notifications route | `backend/app/api/v1/routes/notifications.py` | ✅ | ✅ | |
| Announcements route | `backend/app/api/v1/routes/announcements.py` | ✅ | ✅ | |
| Global markets route | `backend/app/api/v1/routes/global_markets.py` | ✅ | ✅ | |
| Commodities route | `backend/app/api/v1/routes/commodities.py` | ✅ | ✅ | |
| Indices/Funds route | `backend/app/api/v1/routes/indices_funds.py` | ✅ | ✅ | |
| Saved screens route | `backend/app/api/v1/routes/saved_screens.py` | ✅ | ✅ | |
| Admin route | `backend/app/api/v1/routes/admin.py` | ✅ | ✅ | |
| Top 5 route | `backend/app/api/v1/routes/top5.py` | ✅ | ✅ | |
| Auth logic | `backend/app/core/security.py` | ✅ | ✅ | |
| Subscription plans | `backend/app/core/plans.py` | ✅ | ✅ | |
| Config/settings | `backend/app/core/config.py` | ✅ | ✅ | No secrets |
| Cache (Redis) | `backend/app/core/cache.py` | ✅ | ✅ | |
| Dependencies | `backend/app/core/deps.py` | ✅ | ✅ | |
| DB session | `backend/app/db/session.py` | ✅ | ✅ | |
| Email service | `backend/app/services/email.py` | ✅ | ✅ | Confirmation email added V5 |
| SMS service | `backend/app/services/sms.py` | ✅ | ✅ | |
| Notification service | `backend/app/services/notification_service.py` | ✅ | ✅ | |
| Pydantic schemas (8) | `backend/app/schemas/` | ✅ | ✅ | |
| Background workers (18) | `backend/app/workers/` | ✅ | ✅ | |
| Compute engines (25) | `backend/compute/engine/` | ✅ | ✅ | |
| ETL scripts (40+) | `backend/scripts/` | ✅ | ✅ | |
| Python deps | `backend/requirements.txt` | ✅ | ✅ | 46 packages |
| Dockerfile | `backend/Dockerfile` | ✅ | ✅ | |

---

## B. DATABASE ASSETS

| Asset | Location | In Git | Backed Up | Notes |
|-------|----------|--------|-----------|-------|
| Migration 001-056 (60 files) | `database/migrations/` | ✅ | ✅ | Full schema history |
| Post-launch migration: mining/REIT | `backend/migrations/add_mining_reit_capital_raise_tables.sql` | ✅ | ✅ | |
| Post-launch migration: Stripe ID | `backend/migrations/add_stripe_subscription_id.sql` | ✅ | ✅ | |
| Migration runner script | `database/migrate.sh` | ✅ | ✅ | |
| Seed / reference data | Embedded in migration SQL | ✅ | ✅ | |
| Docker DB config | `docker-compose.yml` | ✅ | ✅ | PostgreSQL 16 + TimescaleDB |
| SQLAlchemy session config | `backend/app/db/session.py` | ✅ | ✅ | |
| **Live database data** | Server PostgreSQL | ❌ Git N/A | ⚠️ Manual pg_dump | **Action needed: automate daily backup** |

---

## C. DOCUMENTS & BUSINESS RULES

| Document | Location | In Git | Notes |
|----------|----------|--------|-------|
| Master design plan | `ASX_Screener_Design_Plan.md` | ✅ | v1.0, April 2026 |
| Architecture master | `Design/00_Architecture_Master.md` | ✅ | v5 updated |
| Architecture HLD | `Design/01_Architecture_and_HLD.md` | ✅ | |
| Database design LLD | `Design/02_Database_Design_LLD.md` | ✅ | |
| Data pipeline LLD | `Design/03_Data_Pipeline_LLD.md` | ✅ | |
| Compute engine LLD | `Design/04_Compute_Engine_LLD.md` | ✅ | |
| Project kickoff prereqs | `Design/05_Project_Kickoff_Prerequisites.md` | ✅ | |
| DB hosting options | `Design/06_Database_Hosting_Options.md` | ✅ | |
| Data sizing & DB plan | `Design/07_Data_Sizing_and_DB_Plan.md` | ✅ | |
| Compute schedule strategy | `Design/08_Compute_Engine_Schedule_Strategy.md` | ✅ | |
| Metric compute tags master | `Design/09_Metric_Compute_Tags_Master.md` | ✅ | Scoring/ranking rules |
| Frontend wireframes | `Design/10_Frontend_Wireframes.md` | ✅ | |
| API design | `Design/11_API_Design.md` | ✅ | |
| Legal & compliance | `Design/12_Legal_and_Compliance.md` | ✅ | Updated V5 |
| RBAC & user portal | `Design/13_User_Portal_and_RBAC.md` | ✅ | Subscription/feature gating rules |
| Restore guide V5 | `RESTORE_v5.md` | ✅ | New V5 |
| Restore script V5 | `restore_v5.sh` | ✅ | New V5 |
| Version manifest V5 | `V5_VERSION_MANIFEST.md` | ✅ | **This audit** |
| Inventory checklist V5 | `V5_INVENTORY_CHECKLIST.md` | ✅ | **This audit** |
| Frontend README | `frontend/README.md` | ✅ | |
| Frontend agent guide | `frontend/AGENTS.md` | ✅ | Next.js version notes |
| Docs 100–103 | — | ❌ | **Not found** — no files with this numbering. May be a future planned doc series. |
| `.docx` reference docs (3) | Project root (untracked) | ⚠️ | Store in Google Drive/OneDrive |

---

## D. LEGAL, COMPLIANCE & DISCLAIMERS

| Item | Where it lives | Status |
|------|---------------|--------|
| Privacy Policy page | `/privacy` (live) | ✅ V5 |
| Terms of Service page | `/terms` (live) | ✅ V5 |
| Financial disclaimer | Footer (all pages) | ✅ |
| Not-financial-advice wording | Terms §3, screener AI panel, footer | ✅ |
| AFSL position | Terms §3 explicitly states no AFSL | ✅ |
| Australian Consumer Law rights | Terms §12 | ✅ |
| NSW governing law | Terms §13 | ✅ |
| OAIC reference | Privacy §7 | ✅ |
| Affiliate disclosure (brokers) | Terms §10, brokers page | ✅ |
| Data accuracy disclaimer | Terms §9 | ✅ |
| AI output disclaimer | Screener AI results panel | ✅ V5 |
| ToS acceptance (pre-checkout) | Pricing page | ✅ V5 |
| Legal design doc | `Design/12_Legal_and_Compliance.md` | ✅ |
| Lawyer AFSL review | External | ⚠️ Pending |

---

## E. SETTINGS & CONFIGURATIONS

| Config | In Git | Secret-Free | Notes |
|--------|--------|-------------|-------|
| `.env.example` (root) | ✅ | ✅ | Placeholders only |
| `backend/.env.example` | ✅ | ✅ | Placeholders only |
| `frontend/.env.local` | ⚠️ Not in git | ✅ | API_URL only — add to deploy notes |
| `frontend/next.config.ts` | ✅ | ✅ | |
| `frontend/tsconfig.json` | ✅ | ✅ | |
| `frontend/postcss.config.mjs` | ✅ | ✅ | |
| `frontend/eslint.config.mjs` | ✅ | ✅ | |
| `frontend/package.json` | ✅ | ✅ | |
| `frontend/package-lock.json` | ✅ | ✅ | |
| `backend/requirements.txt` | ✅ | ✅ | |
| `docker-compose.yml` | ✅ | ✅ | |
| Subscription tier config | `backend/app/core/plans.py` | ✅ | ✅ |
| Rate limit config | `backend/app/core/config.py` | ✅ | ✅ |
| JWT config | `backend/app/core/config.py` | ✅ | ✅ |
| Email/support config | `backend/app/core/config.py` | ✅ | ✅ |
| Cron job setup | `backend/scripts/eodhd/v2/jobs/setup_cron.sh` | ✅ | ✅ |
| CI/CD pipeline | `.github/workflows/ci.yml` | ✅ | ✅ |
| Systemd service | `/etc/systemd/system/asx-api.service` (server) | ⚠️ Server only | Back up manually |
| PM2 config | Server PM2 dump (pm2 save) | ⚠️ Server only | Included in `pm2 save` |
| Nginx / reverse proxy | Server only | ⚠️ | Back up `/etc/nginx/` if used |

---

## F. PIPELINES & AUTOMATION

| Pipeline | Location | Status |
|----------|----------|--------|
| Daily price + metrics pipeline | `scripts/eodhd/v2/jobs/daily_pipeline.py` | ✅ |
| Weekly pipeline | `scripts/eodhd/v2/jobs/weekly_pipeline.py` | ✅ |
| Monthly pipeline | `scripts/eodhd/v2/jobs/monthly_pipeline.py` | ✅ |
| Historical download jobs | `scripts/eodhd/v2/jobs/historical_download.py` | ✅ |
| Incremental daily job | `scripts/eodhd/v2/jobs/incremental_daily.py` | ✅ |
| Weekly refresh job | `scripts/eodhd/v2/jobs/weekly_refresh.py` | ✅ |
| Cron configuration | `scripts/eodhd/v2/jobs/setup_cron.sh` | ✅ |
| Pipeline runner | `scripts/eodhd/v2/jobs/pipeline_runner.py` | ✅ |
| Deploy automation | `deploy.sh` | ✅ |
| Restore automation | `restore_v5.sh` | ✅ V5 |
| DB migration runner | `database/migrate.sh` | ✅ |
| CI/CD | `.github/workflows/ci.yml` | ✅ |
| 18 background workers | `backend/app/workers/` | ✅ |
| APScheduler (in-process) | `backend/app/main.py` (lifespan) | ✅ |

---

## G. SECRETS AUDIT

| Check | Result |
|-------|--------|
| Hardcoded API keys in Python | ✅ NONE FOUND |
| Hardcoded API keys in TypeScript | ✅ NONE FOUND |
| Hardcoded passwords in SQL | ✅ NONE FOUND |
| Hardcoded DB connection strings | ✅ NONE FOUND |
| `.env` files committed to git | ✅ NOT COMMITTED |
| Private keys / certs in repo | ✅ NOT FOUND |
| Stripe keys in code | ✅ Config only (env var) |
| JWT secret in code | ✅ Config only (env var) |
| AWS credentials in code | ✅ Config only (env var) |
| `frontend/.env.local` content | ✅ API URL only — no secrets |

**Verdict: ✅ CLEAN — No secrets in repository**

---

## H. SUMMARY COUNTS

| Category | Total Assets | ✅ Versioned | ⚠️ Needs Action | ❌ Missing |
|----------|-------------|------------|----------------|----------|
| Frontend pages/components | 45 | 45 | 0 | 0 |
| Backend routes/services | 35 | 35 | 0 | 0 |
| Compute engines / workers | 43 | 43 | 0 | 0 |
| ETL / pipeline scripts | 50+ | 50+ | 0 | 0 |
| Database migrations | 62 | 62 | 0 | 0 |
| Config files | 16 | 14 | 2 | 0 |
| Documentation files | 20 | 19 | 1 (.docx) | 1 (docs 100-103) |
| Legal / compliance items | 14 | 13 | 1 (lawyer review) | 0 |
| Pipelines / automation | 14 | 14 | 0 | 0 |
| Secrets in repo | 0 | — | — | — |
| **TOTAL** | **~300+** | **~295** | **~4** | **~1** |
