# ASX Screener — V4.0.0 Restore Guide
**Baseline Date:** 2026-05-21  
**Git Tag:** `v4.0.0`  
**Commit:** `73cc25a`  
**GitHub:** https://github.com/PrashanthPadeti/asx-screener

---

## 📦 What's Saved

| Backup | Location | Size | Contains |
|--------|----------|------|----------|
| **Full folder backup** | `C:\Users\Dell\My Claude\Code\ASX_Screener_v4.0.0_Backup_2026-05-21.zip` | ~448 MB | Everything including node_modules, venv cache |
| **Clean git archive** | `C:\Users\Dell\My Claude\Code\ASX_Screener_v4.0.0_git_2026-05-21.zip` | ~1.3 MB | Source code only (no dependencies) |
| **GitHub tag** | https://github.com/PrashanthPadeti/asx-screener/releases/tag/v4.0.0 | — | Full git history + tag |
| **GitHub main branch** | https://github.com/PrashanthPadeti/asx-screener | — | Always latest |

---

## ⚡ Quick Restore — 3 Scenarios

---

### Scenario A: "Something broke on the server — rollback to v3.1.0"

```bash
# SSH into server
ssh root@your-server-ip

# Navigate to app
cd /opt/asx-screener

# Check current state
git log --oneline -5

# Option 1: Reset to v3.1.0 tag (safest)
git fetch --tags
git checkout v3.1.0

# Restart backend
pm2 restart asx-backend
pm2 logs asx-backend --lines 20

# Option 2: If you need to go back to main and redeploy
git checkout main
git reset --hard v3.1.0
git push origin main --force   # only if absolutely needed
pm2 restart asx-backend
```

---

### Scenario B: "Local code is messed up — restore from git tag"

```bash
# In Windows terminal, navigate to project
cd "C:\Users\Dell\My Claude\Code\ASX Screener"

# Discard all local changes and go back to v3.1.0
git fetch --tags
git checkout v3.1.0

# Or if you want to restore main branch to v3.1.0 state
git checkout main
git reset --hard v3.1.0
```

---

### Scenario C: "Fresh install on a new server from scratch"

#### Step 1 — Clone the repo
```bash
git clone https://github.com/PrashanthPadeti/asx-screener.git /opt/asx-screener
cd /opt/asx-screener
git checkout v3.1.0
```

#### Step 2 — Python environment
```bash
python3 -m venv /opt/asx-screener/asx-venv
source /opt/asx-screener/asx-venv/bin/activate
pip install -r backend/requirements.txt
```

#### Step 3 — Environment variables
```bash
# Create .env file in /opt/asx-screener/backend/
cp backend/.env.example backend/.env
# Edit with your actual values:
nano backend/.env
```

Required `.env` variables:
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/asx_screener
REDIS_URL=redis://localhost:6379
SECRET_KEY=your-secret-key
REFRESH_SECRET_KEY=your-refresh-secret
EODHD_API_KEY=your-eodhd-key
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
RESEND_API_KEY=re_...
ADMIN_EMAILS=asxscreener@gmail.com
```

#### Step 4 — Database
```bash
# Create DB and run all migrations in order
sudo -u postgres psql -c "CREATE DATABASE asx_screener;"
sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# Run migrations 001 → latest
for f in database/migrations/*.sql; do
    sudo -u postgres psql -d asx_screener -f "$f"
    echo "Applied: $f"
done
```

#### Step 5 — Frontend
```bash
cd frontend
npm install
npm run build
```

#### Step 6 — Start with PM2
```bash
# Backend
pm2 start /opt/asx-screener/backend/start_backend.sh --name asx-backend

# Frontend
pm2 start "npm start" --name asx-frontend --cwd /opt/asx-screener/frontend

pm2 save
pm2 startup
```

#### Step 7 — Verify Pipeline Monitor
Open: `https://yourdomain.com/admin` → Pipeline Monitor  
All 14 jobs should show **Healthy** after the daily scheduler runs.

---

## 🏷️ All Version Tags

| Tag | Date | Description |
|-----|------|-------------|
| `v1.0-base` | 2026-05-04 | Base: portfolio, AI insights, 5-tier plans, screener |
| `v2.0.0` | 2026-05-09 | Screener, market overview, AI query, anomalies, all pipelines |
| `v3.0.0` | 2026-05-13 | Redis caching, period return fixes, pipeline monitor, DB indexes |
| `v3.1.0` | 2026-05-21 | Pipeline heartbeat system, ASIC fix, subscription enforcement |
| `v4.0.0` | 2026-05-21 | **← CURRENT** Production-verified stable — all fixes, 14 jobs healthy |

### Jump between versions (local)
```bash
# See all tags
git tag -l

# Switch to any version
git checkout v2.0.0    # go back to V2
git checkout v3.0.0    # go back to V3.0
git checkout v4.0.0    # this baseline
git checkout main      # latest
```

---

## 🗄️ Database Backup (Server)

### Create a DB backup on the server
```bash
# Full database dump
sudo -u postgres pg_dump asx_screener > /opt/backups/asx_screener_$(date +%Y%m%d).sql

# Compressed
sudo -u postgres pg_dump asx_screener | gzip > /opt/backups/asx_screener_$(date +%Y%m%d).sql.gz
```

### Restore DB from backup
```bash
sudo -u postgres psql -d asx_screener < /opt/backups/asx_screener_20260521.sql
```

---

## ✅ Health Check After Restore

Run these to verify everything is working:

```bash
# 1. Backend running?
pm2 status

# 2. API responding?
curl http://localhost:8000/health

# 3. DB connected?
sudo -u postgres psql -d asx_screener -c "SELECT COUNT(*) FROM screener.universe WHERE status='active';"

# 4. All 7 heartbeat jobs registered?
sudo -u postgres psql -d asx_screener -c "SELECT job_id, last_run_at FROM meta.job_heartbeat ORDER BY last_run_at DESC;"

# 5. Redis working?
redis-cli ping   # should return PONG

# 6. Check recent logs
pm2 logs asx-backend --lines 30
```

Expected healthy output:
- `screener.universe` count: ~2,100+ rows
- `meta.job_heartbeat`: 7 rows (index_prices, global_markets, commodities, asx_index_flags, asx_announcements, short_positions, price_alerts)
- Redis: `PONG`
- pm2: both asx-backend and asx-frontend `online`

---

## 📋 Key File Locations

| Component | Path |
|-----------|------|
| Backend FastAPI app | `backend/app/main.py` |
| API routes | `backend/app/api/v1/routes/` |
| Workers (schedulers) | `backend/app/workers/` |
| Compute engines | `backend/compute/engine/` |
| Database migrations | `database/migrations/` |
| Frontend Next.js | `frontend/` |
| ASIC scripts | `scripts/asic/` |
| EODHD scripts | `scripts/eodhd/` |
| Daily pipeline | `scripts/eodhd/v2/jobs/daily_pipeline.py` |
| PM2 config | `ecosystem.config.js` |
| Nginx config | `nginx/` |
