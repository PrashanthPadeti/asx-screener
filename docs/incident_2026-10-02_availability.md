# Incident — 2 Oct 2026 — site unavailable, ~40 minutes, found by a human

Production returned Cloudflare **504 Gateway Time-out** (`Host Error`) at
**09:50:37 UTC**. The outage was discovered because the operator tried to sign
in and could not. Nothing in the system reported it.

Service was restored at ~13:36 UTC by restarting `asx-backend` and
`asx-frontend`. Restart was performed **after** read-only evidence capture, so
the diagnosis below rests on observations taken while the fault was live plus
the retained application log.

---

## What was observed, while the fault was live

| Observation | Value |
|---|---|
| `curl localhost:8000/health` | `000` (no response within 5s) |
| `curl localhost:3000` | `000` (no response within 5s) |
| `curl localhost:80` | `301` — nginx healthy |
| `ss -ltnp` on :8000 | `LISTEN 35 2048` — **35 connections queued, unaccepted** |
| `systemctl is-active` | `asx-backend`, `nginx`, `postgresql` all **active** |
| Disk | 73% used, 22 GB available |
| Memory | 3.8 Gi total, 2.5 Gi available |
| OOM killer | no entries |
| Postgres connections | 14 total (7 idle, 1 active) |
| Longest running query | `00:00:00` — none |

The backend was listening and accepting sockets while answering none. The
frontend returned nothing because it server-renders through that backend.
nginx was healthy and had nothing to proxy to.

## What the application log shows

`backend.log` (the service writes to `/opt/asx-screener/logs/backend.log` via
`StandardOutput=append`, **not** journald) was **not** silent:

    lines logged between 09:41 and 09:55 UTC : 155

Their content, continuing until 10:05 UTC, is hundreds of sequential outbound
calls at roughly two per second:

    GET https://eodhd.com/api/news?s=<CODE>.AU ... "HTTP/1.1 200 OK"

terminating in:

    10:05:50  Announcement worker: 2 inserted, 257 skipped (irrelevant), 1 market-sensitive
    10:05:51  Job "fetch_announcements (trigger: cron[hour='19', minute='10'])" executed successfully

`19:10 AEST` is `09:10 UTC`. So a single scheduled job ran roughly
**09:10 → 10:05 UTC (~55 minutes)**, performing hundreds of serial external
HTTP requests **inside the API process**, and the 504 at 09:50 UTC falls inside
that window. `daily_pipeline` (08:30 → 09:41 UTC, "complete in 71.5 min")
overlapped its first half.

`/health` reports `"schedulers": {"jobs": 19}` — these jobs run in-process with
the request-serving application.

## Classification

**Co-locating long-running external-I/O jobs with the request-serving process
is an availability defect.** The evidence establishes:

* a ~55-minute in-process job performing hundreds of outbound calls,
* HTTP requests queueing unanswered (`Recv-Q 35`) while it ran,
* the outage window contained within the job's window.

It does **not** establish *which* shared resource was exhausted. Event loop,
threadpool, DB pool, CPU and socket limits are all candidates, and nothing
measured distinguishes them. The mechanism is deliberately left unspecified
until it is measured; the co-location is sufficient to act on.

Specifically ruled out by measurement: disk exhaustion, memory exhaustion, the
OOM killer, database connection saturation, and long-running queries.

**Not caused by the v11.1.1 deploy.** The deploy landed ~10 hours earlier and
the failing job is pre-existing scheduled work.

## Two wrong diagnoses, recorded because the pattern matters

1. **Disk exhaustion.** Five full backups (~974 MB each) had been taken that
   day, which made a full disk feel obvious. Measurement: 22 GB free.
2. **Database connection-pool exhaustion**, attributed to the public homepage
   issuing an uncached screener query per request. Measurement: 14 connections,
   one active, no long queries.

Both were reasoned from what had recently been changed rather than from what
the system was doing, and both were stated with a confident mechanism attached.
The third attempt began by reading the log and was the first to be supported.

A further misread: `journalctl -u asx-backend` returned "No entries", which was
briefly treated as evidence of a silent, wedged process. The service does not
log to journald at all. Absence of evidence in the wrong place is not evidence.

## Standing defects the log exposed (separate from this incident)

    06:13 → 07:28 (every 15 min)  alert_worker: Object of type Decimal is not JSON serializable
    10:05  top5_strategy_worker:  role "root" does not exist
    10:05  short_positions:       DATABASE_URL not set
    10:05  announcement_worker:   syntax error at or near ":"
           ERROR: Exception in ASGI application  (x2)

Three are in-process workers that cannot reach the database (missing
environment, wrong role, malformed SQL). `alert_worker` has been failing on a
quarter-hour cycle. **It is not to be repaired as incidental noise**: first
establish whether it forms part of the protected anomaly-delivery path, and if
so keep it under the existing alert-restoration gate.

## Remediation, in priority order

1. **External uptime monitoring.** Must run outside this host and outside the
   application stack it observes. Probe the public homepage and one uncached
   API path (`/api/v1/market/summary`), asserting status, latency and a minimal
   body property. Alert on sustained failure, not a single transient, and
   record recovery. This closes the detection gap regardless of cause.
2. **Move long-running external-I/O jobs out of the API process**, beginning
   with `fetch_announcements`. Classify all 19 scheduled jobs by runtime and
   side effects first; move the long or blocking ones to a separate execution
   authority with its own logs and failure state. Do not redesign all 19 at
   once.
3. **Triage the standing worker defects** individually, after isolation, with
   the alert/anomaly path excluded until classified.

Additionally: `/system-health` should expose **last start, last finish,
duration and status per scheduled job**. It already reports scheduler identity
and job count. The operationally useful question is whether a job has been
running for 55 minutes or has failed 20 times consecutively — either would have
made this incident visible before the site became unusable.

## Detection gap

The site was unavailable for approximately 40 minutes and the system reported
nothing. `assert_output_freshness` asserts that data is current; nothing
asserts that the site answers. The freshness rule — output freshness proves
scheduled-job health — has no availability counterpart.
