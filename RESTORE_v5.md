# ASX Screener — Restore Guide for v5.0.0

**Version:** v5.0.0  
**Date tagged:** 2026-05-24  
**Use this guide when:** Something breaks after a future deploy and you need to roll back to the last known good state.

---

## What is in v5.0.0

| Area | What was shipped |
|------|-----------------|
| **Legal** | Privacy Policy (`/privacy`), Terms of Service (`/terms`) |
| **Footer** | Legal links on every page (Terms, Privacy, Contact, Brokers, etc.) |
| **Contact Support** | Guest access, 9 categories, confirmation email, system context tracking |
| **Education Hub** | Beginner pathway, 3 SEO articles, analytics events, coming-soon fix |
| **Broker Compare** | Sortable table, quick-pick, filter chips, pros/cons cards |
| **Metrics Glossary** | Pro+ badge, expand/collapse, rich metric cards |
| **Screener** | AI results disclaimer |
| **Pricing** | ToS acceptance note before checkout |

---

## Before You Restore — Read This First

> ⚠️ **The restore script only rolls back application code — NOT the database.**  
> If a future version runs a database migration (new table, new column), rolling back the code  
> will leave the database in the newer state. This is usually fine (old code ignores new columns)  
> but be aware of it.

**When to restore vs when to fix forward:**

| Situation | Recommendation |
|-----------|---------------|
| Frontend build error | Fix forward — faster than a full restore |
| Backend crashes on start | Restore if you can't find the bug in 15 min |
| Data corruption / wrong queries | Restore immediately |
| Users can't log in / pay | Restore immediately |
| Minor UI bug | Fix forward |

---

## Option A — Quick Restore (Recommended)

SSH into the server and run:

```bash
# 1. Go to the project directory
cd /opt/asx-screener

# 2. Run the restore script (dry run first to check)
./restore_v5.sh --check

# 3. If check looks good, run the actual restore
./restore_v5.sh
```

Type `yes` when prompted. The script will:
1. Back up current code to `/opt/backups/pre_restore_<timestamp>.zip`
2. Fetch the v5.0.0 tag from GitHub
3. Check out v5.0.0
4. Restart the backend (systemd)
5. Rebuild and restart the frontend (PM2)
6. Run health checks

---

## Option B — Manual Restore (Step by Step)

If the script fails for any reason, do it manually:

### Step 1 — Back up current code
```bash
mkdir -p /opt/backups
cd /opt/asx-screener
git archive --format=zip --output="/opt/backups/pre_restore_$(date +%Y%m%d_%H%M%S).zip" HEAD
```

### Step 2 — Fetch tags and check out v5.0.0
```bash
cd /opt/asx-screener
git fetch --tags
git checkout v5.0.0
```

### Step 3 — Restart backend
```bash
sudo systemctl restart asx-api
sleep 5
sudo systemctl status asx-api
```

### Step 4 — Rebuild frontend
```bash
cd /opt/asx-screener/frontend
npm ci
npm run build
cp -r .next/static  .next/standalone/.next/static
cp -r public        .next/standalone/public
```

### Step 5 — Restart frontend
```bash
pm2 restart asx-frontend
pm2 save --force
sleep 3
pm2 list
```

### Step 6 — Health check
```bash
curl http://localhost:8000/health
curl http://localhost:3000
```

---

## After Restoring — Verify the Site

Check these pages are working:

| URL | What to verify |
|-----|---------------|
| `asxscreener.com.au` | Home page loads |
| `asxscreener.com.au/screener` | Screener loads, filters work |
| `asxscreener.com.au/terms` | Terms of Service page loads |
| `asxscreener.com.au/privacy` | Privacy Policy page loads |
| `asxscreener.com.au/pricing` | Pricing page loads, ToS note visible |
| `asxscreener.com.au/contact` | Contact form loads |
| `asxscreener.com.au/brokers` | Broker compare page loads |

---

## Returning to Latest After Restore

Once you've fixed the issue causing the rollback:

```bash
cd /opt/asx-screener
git checkout main
./deploy.sh
```

---

## Backup Files

| File | Location | What it is |
|------|----------|------------|
| `ASX_Screener_v5.0.0_backup.zip` | `/opt/backups/` (server) | v5.0.0 code snapshot |
| `ASX_Screener_v5.0.0_git_2026-05-24.zip` | `C:\Users\Dell\My Claude\Code\ASX Screener\` (your PC) | Same snapshot, local copy |
| `pre_restore_<timestamp>.zip` | `/opt/backups/` (server) | Created at restore time — snapshot of whatever was live |

---

## Service Commands Reference

```bash
# Backend
sudo systemctl status asx-api        # check status
sudo systemctl restart asx-api       # restart
sudo journalctl -u asx-api -n 50     # view last 50 log lines
sudo journalctl -u asx-api -f        # follow live logs

# Frontend
pm2 list                             # list all processes
pm2 restart asx-frontend             # restart
pm2 logs asx-frontend                # view logs
pm2 logs asx-frontend --lines 50     # last 50 lines

# Full deploy (back to latest main)
cd /opt/asx-screener && ./deploy.sh
```

---

## Git Version Reference

```
v1.0-base  — Initial foundation
v2.0.0     — Core screener features
v3.0.0     — Major feature expansion
v3.1.0     — Incremental improvements
v4.0.0     — Previous milestone
v5.0.0     — Commercial launch ready ← YOU ARE RESTORING TO THIS
```

To see what changed between versions:
```bash
git log v4.0.0..v5.0.0 --oneline
```
