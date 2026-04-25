# ASX Screener — Database Hosting: Cloud vs Physical

> Version 1.0 | April 2026

---

## The Critical Constraint First

Before comparing options, you must understand one important fact:

```
┌─────────────────────────────────────────────────────────────────────┐
│  ⚠️  CRITICAL: TimescaleDB is NOT supported by most managed          │
│     cloud PostgreSQL services (RDS, Supabase, Cloud SQL, Azure DB)  │
│                                                                      │
│  TimescaleDB requires loading as a shared library at startup:        │
│  shared_preload_libraries = 'timescaledb'                           │
│                                                                      │
│  Fully managed services lock this configuration — they don't        │
│  allow third-party extensions that modify the PostgreSQL core.       │
│                                                                      │
│  Services that DO support TimescaleDB:  ✅                           │
│    • TimescaleDB Cloud (timescale.com)  — purpose-built             │
│    • Aiven for PostgreSQL              — supports extension add-ons  │
│    • Railway.app                       — extension-permissive        │
│    • Self-managed PostgreSQL on any VM — full control               │
│    • Physical server                   — full control               │
│                                                                      │
│  Services that do NOT support TimescaleDB:  ❌                       │
│    • AWS RDS for PostgreSQL                                          │
│    • AWS Aurora PostgreSQL                                           │
│    • Supabase                                                        │
│    • Azure Database for PostgreSQL                                   │
│    • Google Cloud SQL for PostgreSQL                                 │
│    • Neon (serverless PostgreSQL)                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Option Landscape

```
DATABASE HOSTING OPTIONS
│
├── A. CLOUD — Managed Service (they manage the DB for you)
│   ├── A1. TimescaleDB Cloud         ← Best managed option
│   ├── A2. Aiven for PostgreSQL      ← Good alternative
│   └── A3. Railway.app               ← Best for development/MVP
│
├── B. CLOUD — Self-Managed (you install PostgreSQL on a cloud VM)
│   ├── B1. AWS EC2 + PostgreSQL      ← Best for Phase 3 scale
│   ├── B2. DigitalOcean Droplet      ← Best value for Phase 2
│   └── B3. Azure/GCP VM              ← Alternative to AWS
│
└── C. PHYSICAL — On-Premise / Dedicated Server
    ├── C1. Your own server (home/office)
    ├── C2. Colocation (your hardware, data centre space)
    └── C3. Dedicated bare-metal server (Hetzner, OVH, Vultr)
```

---

## Detailed Option Comparison

### Option A1 — TimescaleDB Cloud (timescale.com) ⭐ RECOMMENDED MANAGED

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIMESCALEDB CLOUD                                                   │
│  timescale.com                                                       │
├─────────────────────────────────────────────────────────────────────┤
│  What it is:                                                         │
│  The official managed service from the makers of TimescaleDB.        │
│  Built on top of PostgreSQL 16, fully managed, all TimescaleDB       │
│  features enabled out of the box.                                   │
│                                                                      │
│  Key Features:                                                       │
│  ✅ PostgreSQL 16                                                    │
│  ✅ TimescaleDB (all features: hypertables, compression, etc.)       │
│  ✅ pgvector (AI embeddings)                                         │
│  ✅ Automatic backups (daily, retained 7–30 days)                   │
│  ✅ Point-in-time recovery                                           │
│  ✅ Connection pooling built-in                                      │
│  ✅ Monitoring dashboard                                             │
│  ✅ Sydney region available (AWS ap-southeast-2)                    │
│  ✅ Free trial: 30 days, no credit card                              │
│                                                                      │
│  Pricing (USD/month, billed monthly):                               │
│  ┌─────────────────┬────────┬────────┬───────────────────────────┐  │
│  │ Plan            │ RAM    │ Storage│ Price (USD/mo)            │  │
│  ├─────────────────┼────────┼────────┼───────────────────────────┤  │
│  │ Dev (free trial)│ 1 GB   │ 10 GB  │ Free (30 days)            │  │
│  │ Launch          │ 4 GB   │ 25 GB  │ ~$95/mo                   │  │
│  │ Growth          │ 8 GB   │ 50 GB  │ ~$190/mo                  │  │
│  │ Scale           │ 16 GB  │ 100 GB │ ~$380/mo                  │  │
│  │ Production      │ 32 GB  │ 200 GB │ ~$750/mo                  │  │
│  └─────────────────┴────────┴────────┴───────────────────────────┘  │
│  Note: TimescaleDB compression reduces price significantly.          │
│  Our 100 GB uncompressed = ~10 GB compressed = Launch plan is fine  │
│                                                                      │
│  Australian Data Residency: ✅ Sydney AWS region                    │
│                                                                      │
│  PROS:                                                               │
│  + Zero operational overhead — they handle everything               │
│  + Built specifically for time-series financial data                │
│  + All TimescaleDB features available                               │
│  + Excellent performance out of the box                             │
│  + Auto-scaling storage                                             │
│                                                                      │
│  CONS:                                                               │
│  - More expensive than self-managed                                  │
│  - Vendor lock-in (though data portable — standard PostgreSQL)      │
│  - Limited to their supported PostgreSQL extensions                 │
│                                                                      │
│  Best for: Phase 2 launch onwards                                   │
│  Connection string: postgres://user:pass@host.tsdb.cloud:5432/db   │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Option A2 — Aiven for PostgreSQL ⭐ GOOD ALTERNATIVE

```
┌─────────────────────────────────────────────────────────────────────┐
│  AIVEN FOR POSTGRESQL                                                │
│  aiven.io                                                            │
├─────────────────────────────────────────────────────────────────────┤
│  What it is:                                                         │
│  Multi-cloud managed database service. Supports PostgreSQL 16        │
│  with TimescaleDB as an add-on extension.                           │
│                                                                      │
│  Key Features:                                                       │
│  ✅ PostgreSQL 16                                                    │
│  ✅ TimescaleDB extension (enabled via dashboard toggle)             │
│  ✅ pgvector                                                         │
│  ✅ Choice of cloud: AWS, GCP, Azure                                │
│  ✅ Sydney region available (AWS ap-southeast-2)                    │
│  ✅ Automatic backups                                                │
│  ✅ Free trial: $300 credit (30 days)                               │
│  ✅ Can deploy Redis, Elasticsearch on same platform                │
│                                                                      │
│  Pricing (USD/month):                                               │
│  ┌──────────────┬────────┬────────┬──────────────────────────────┐  │
│  │ Plan         │ RAM    │ Storage│ Price (USD/mo)               │  │
│  ├──────────────┼────────┼────────┼──────────────────────────────┤  │
│  │ Hobbyist     │ 1 GB   │ 5 GB   │ ~$19/mo                      │  │
│  │ Startup      │ 2 GB   │ 20 GB  │ ~$48/mo                      │  │
│  │ Business     │ 8 GB   │ 80 GB  │ ~$186/mo                     │  │
│  │ Premium      │ 16 GB  │ 175 GB │ ~$370/mo                     │  │
│  └──────────────┴────────┴────────┴──────────────────────────────┘  │
│                                                                      │
│  PROS:                                                               │
│  + Cheaper than TimescaleDB Cloud                                   │
│  + Can host Redis + OpenSearch on same platform                     │
│  + Flexible cloud provider choice                                   │
│  + Good documentation                                               │
│                                                                      │
│  CONS:                                                               │
│  - TimescaleDB is add-on, not native (minor limitation)             │
│  - UI less polished than TimescaleDB Cloud                          │
│                                                                      │
│  Best for: Phase 1–2 (startup budget)                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Option A3 — Railway.app (Best for Development Phase)

```
┌─────────────────────────────────────────────────────────────────────┐
│  RAILWAY.APP                                                         │
│  railway.app                                                         │
├─────────────────────────────────────────────────────────────────────┤
│  What it is:                                                         │
│  Modern developer-focused platform. Deploy any Docker image.         │
│  Supports full PostgreSQL with any extension including TimescaleDB. │
│                                                                      │
│  Key Features:                                                       │
│  ✅ PostgreSQL 16 (via official Docker image)                        │
│  ✅ TimescaleDB (via timescale/timescaledb-ha:pg16 image)            │
│  ✅ pgvector                                                         │
│  ✅ Deploy API + Redis + Workers all on same platform               │
│  ✅ Git-based deployments (push to deploy)                          │
│  ⚠️  No Sydney region — US West / EU only                           │
│  ✅ Free $5 credit/month on Hobby plan                               │
│                                                                      │
│  Pricing:                                                            │
│  Hobby:  $5/month + usage (~$0.000463/GB-hour RAM, $0.10/GB storage)│
│  Pro:    $20/month + usage                                           │
│  Estimated total for dev: $15–30/month                              │
│                                                                      │
│  PROS:                                                               │
│  + Extremely easy to deploy and use                                 │
│  + Very cheap for development                                       │
│  + Deploy entire stack (API + DB + Redis + Airflow) in one place    │
│  + Great DX (developer experience)                                  │
│                                                                      │
│  CONS:                                                               │
│  ⚠️  No Australian/Sydney region (latency issue for production)     │
│  - Not suitable for production (no SLA, limited support)            │
│  - Not appropriate for storing sensitive Australian financial data  │
│                                                                      │
│  Best for: Local development + staging only. NOT production.         │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Option B1 — AWS EC2 + Self-Managed PostgreSQL ⭐ BEST FOR SCALE

```
┌─────────────────────────────────────────────────────────────────────┐
│  AWS EC2 + SELF-MANAGED POSTGRESQL + TIMESCALEDB                    │
│  aws.amazon.com                                                      │
├─────────────────────────────────────────────────────────────────────┤
│  What it is:                                                         │
│  You rent a virtual machine from AWS in Sydney (ap-southeast-2)      │
│  and install PostgreSQL 16 + TimescaleDB yourself.                  │
│  AWS manages the hardware; you manage the software.                 │
│                                                                      │
│  Setup:                                                              │
│  1. Launch EC2 instance (Ubuntu 24.04)                              │
│  2. Install PostgreSQL 16                                            │
│  3. Install TimescaleDB via apt package                              │
│  4. Configure postgresql.conf                                        │
│  5. Set up automated backups to S3                                   │
│  6. Set up monitoring (CloudWatch)                                   │
│                                                                      │
│  Recommended Instance Types (Sydney region):                        │
│  ┌──────────────────┬────────┬────────┬──────────────────────────┐  │
│  │ Instance         │ RAM    │ vCPUs  │ Price (AUD/mo, on-demand)│  │
│  ├──────────────────┼────────┼────────┼──────────────────────────┤  │
│  │ t3.medium        │ 4 GB   │ 2      │ ~$50/mo  ← Phase 1 dev  │  │
│  │ t3.large         │ 8 GB   │ 2      │ ~$100/mo ← Phase 2 MVP  │  │
│  │ r6g.xlarge       │ 32 GB  │ 4      │ ~$250/mo ← Phase 2 prod │  │
│  │ r6g.2xlarge      │ 64 GB  │ 8      │ ~$490/mo ← Phase 3      │  │
│  │ r6g.4xlarge      │ 128 GB │ 16     │ ~$970/mo ← Phase 3 max  │  │
│  └──────────────────┴────────┴────────┴──────────────────────────┘  │
│  Note: Reserved instances (1-yr): 40% cheaper than on-demand        │
│  Note: EBS gp3 storage: ~$0.11 AUD/GB/month                        │
│                                                                      │
│  Add: AWS RDS Multi-AZ standby for high availability (~2× price)   │
│                                                                      │
│  PROS:                                                               │
│  + Full control over PostgreSQL configuration                       │
│  + Any extension including TimescaleDB                              │
│  + Sydney region — data stays in Australia                          │
│  + Cost-effective at scale with Reserved instances                  │
│  + Integrates perfectly with rest of AWS stack                      │
│  + Can use EBS snapshots for automated backups                      │
│                                                                      │
│  CONS:                                                               │
│  - You manage everything: upgrades, patching, backups, HA           │
│  - Requires Linux/PostgreSQL administration knowledge               │
│  - If server crashes, you manage recovery                           │
│  - Security patching is your responsibility                         │
│                                                                      │
│  Best for: Phase 2–3 (when you have tech skills and budget control) │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Option B2 — DigitalOcean Droplet ⭐ BEST VALUE SELF-MANAGED

```
┌─────────────────────────────────────────────────────────────────────┐
│  DIGITALOCEAN DROPLET + POSTGRESQL + TIMESCALEDB                    │
│  digitalocean.com                                                    │
├─────────────────────────────────────────────────────────────────────┤
│  What it is:                                                         │
│  Simple, affordable Linux VMs. Very developer-friendly.             │
│  Sydney (AUS) datacenter available.                                 │
│                                                                      │
│  Recommended Droplets for Database:                                 │
│  ┌──────────────────┬────────┬────────┬──────────────────────────┐  │
│  │ Droplet          │ RAM    │ vCPUs  │ Price (USD/mo)           │  │
│  ├──────────────────┼────────┼────────┼──────────────────────────┤  │
│  │ Basic 4GB        │ 4 GB   │ 2      │ $24/mo ← Dev start      │  │
│  │ General 8GB      │ 8 GB   │ 2      │ $48/mo ← Phase 2        │  │
│  │ Memory 16GB      │ 16 GB  │ 2      │ $84/mo ← Phase 2 prod   │  │
│  │ Memory 32GB      │ 32 GB  │ 4      │ $168/mo ← Phase 3       │  │
│  └──────────────────┴────────┴────────┴──────────────────────────┘  │
│  + SSD Block Storage: $0.10/GB/mo                                   │
│  + Automated backups: +20% of droplet price                        │
│                                                                      │
│  DigitalOcean also offers Managed PostgreSQL ($25/mo start)         │
│  BUT: Managed version does NOT support TimescaleDB                  │
│  So: Use a Droplet (VM) with self-installed PostgreSQL + TimescaleDB│
│                                                                      │
│  PROS:                                                               │
│  + Cheapest option with Sydney region                               │
│  + Very simple UI for beginners                                     │
│  + Good documentation and community                                 │
│  + $200 free credit for new accounts                                │
│  + Simple, predictable pricing                                      │
│                                                                      │
│  CONS:                                                               │
│  - Self-managed (same as AWS EC2 but less enterprise features)      │
│  - Less mature than AWS for enterprise HA setups                    │
│  - No reserved pricing discounts                                    │
│                                                                      │
│  Best for: Phase 2 launch (cheapest production-grade option)        │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Option C — Physical / On-Premise Server

```
┌─────────────────────────────────────────────────────────────────────┐
│  PHYSICAL / ON-PREMISE DATABASE SERVER                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  C1. YOUR OWN SERVER (Home/Office)                                  │
│  ────────────────────────────────                                   │
│  Hardware needed for our workload:                                  │
│  CPU:     8+ cores (Intel Xeon or AMD EPYC recommended)             │
│  RAM:     32 GB minimum, 64 GB recommended                          │
│  Storage: 2× 2TB NVMe SSD in RAID-1 (mirroring for safety)         │
│           Primary + backup drive                                     │
│  Network: 100 Mbps+ NBN business connection                         │
│  UPS:     Uninterruptible Power Supply (essential)                  │
│                                                                      │
│  Hardware Cost: $3,000–8,000 AUD (one-time)                        │
│  Running Cost:  ~$200–400 AUD/mo (electricity + internet)          │
│  NBN Business:  ~$100–200 AUD/mo (fixed IP needed)                 │
│                                                                      │
│  CRITICAL ISSUES:                                                    │
│  ❌ Single point of failure (disk dies = data loss if no RAID)      │
│  ❌ Power outage = downtime (need generator or UPS)                 │
│  ❌ Home internet is NOT reliable for a live website                │
│  ❌ No redundancy — one hardware failure = hours/days of downtime   │
│  ❌ Security risk — your home/office IP exposed to internet         │
│  ❌ You must physically be there to fix hardware issues             │
│  ❌ Cannot scale on demand                                          │
│  ❌ Paying users will not accept downtime due to power/hardware     │
│                                                                      │
│  ──────────────────────────────────────────────────────────────     │
│                                                                      │
│  C2. COLOCATION (Your hardware, Data Centre space)                  │
│  ─────────────────────────────────────────────────                  │
│  You buy the server → rent rack space in a Sydney data centre       │
│  Data centres: Equinix SY1/SY2/SY3, NextDC S1/S2, NEXTDC M2       │
│                                                                      │
│  Hardware Cost:  $3,000–8,000 AUD (one-time)                       │
│  Colo Cost:      $300–800 AUD/mo (1U rack space + power + network) │
│  Network:        Data centre provides redundant internet             │
│                                                                      │
│  BETTER than home server because:                                   │
│  ✅ Redundant power (generator backup)                              │
│  ✅ Redundant internet (multiple ISP connections)                   │
│  ✅ Physical security                                               │
│  ✅ Data stays in Australia (Sydney)                                │
│  ✅ Low latency for Sydney-based users                              │
│                                                                      │
│  STILL problematic because:                                         │
│  ❌ High upfront hardware cost                                      │
│  ❌ Hardware failure = you drive to the data centre to fix it       │
│  ❌ No easy scaling (buy new hardware to grow)                      │
│  ❌ Ongoing operational burden (OS updates, hardware monitoring)    │
│                                                                      │
│  ──────────────────────────────────────────────────────────────     │
│                                                                      │
│  C3. DEDICATED BARE-METAL SERVER (Hetzner, OVH)                    │
│  ────────────────────────────────────────────────                   │
│  Rent a physical server from a hosting provider.                    │
│  You manage the OS + software, they manage the hardware.            │
│                                                                      │
│  Hetzner Dedicated (Germany/Finland — no AUS):                     │
│  EX44: 64GB RAM, 2×512GB NVMe → $80 USD/mo ← incredible value     │
│  AX102: 128GB RAM, 2×3.84TB SSD → $250 USD/mo                     │
│                                                                      │
│  OVH (Sydney available):                                            │
│  RISE-1: 32GB RAM, 2×480GB SSD → ~$120 AUD/mo                     │
│  ADVANCE-2: 64GB RAM, 2×960GB SSD → ~$250 AUD/mo                  │
│                                                                      │
│  PROS of dedicated bare-metal:                                      │
│  ✅ No noisy neighbours (dedicated hardware — you get all CPU/RAM)  │
│  ✅ Very high performance per dollar                                │
│  ✅ Full control over OS and software                               │
│  ✅ TimescaleDB works perfectly                                     │
│  ✅ Great for heavy compute (Compute Engine batch jobs)             │
│                                                                      │
│  CONS:                                                               │
│  ❌ Cannot scale instantly (need to order new server, 1–2 hr setup) │
│  ❌ Hardware failure → provider replaces, but you restore data      │
│  ❌ You manage all software, OS, security patches                   │
│  ❌ No managed backups (you set up your own)                        │
│                                                                      │
│  Best for: Phase 3 compute-heavy workloads (the Compute Engine)    │
│            e.g. Hetzner for Celery/Airflow workers                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Head-to-Head Comparison Table

```
┌───────────────────┬────────┬────────┬────────┬────────┬────────┬────────┬────────┐
│ Criterion         │Timescale│ Aiven  │Railway │AWS EC2 │  DO    │Physical│Dedicated│
│                   │ Cloud  │        │        │        │ Droplet│(home)  │Bare Metal│
├───────────────────┼────────┼────────┼────────┼────────┼────────┼────────┼────────┤
│ PostgreSQL 16     │  ✅    │  ✅    │  ✅    │  ✅    │  ✅    │  ✅    │  ✅   │
│ TimescaleDB       │  ✅    │  ✅    │  ✅    │  ✅    │  ✅    │  ✅    │  ✅   │
│ pgvector (AI)     │  ✅    │  ✅    │  ✅    │  ✅    │  ✅    │  ✅    │  ✅   │
│ Managed backups   │  ✅    │  ✅    │  ✅    │  ⚠️DIY │  ⚠️DIY │  ❌DIY │  ❌DIY│
│ Auto-failover HA  │  ✅    │  ✅    │  ❌    │  ⚠️DIY │  ⚠️DIY │  ❌    │  ❌   │
│ Sydney region     │  ✅    │  ✅    │  ❌    │  ✅    │  ✅    │  ✅    │  ⚠️  │
│ AUS data residency│  ✅    │  ✅    │  ❌    │  ✅    │  ✅    │  ✅    │  ⚠️  │
│ Zero ops overhead │  ✅    │  ✅    │  ✅    │  ❌    │  ❌    │  ❌    │  ❌   │
│ Instant scale     │  ✅    │  ✅    │  ✅    │  ✅    │  ✅    │  ❌    │  ❌   │
│ Cost (Phase 2)    │  $$    │  $     │  $     │  $$    │  $     │  $$$   │  $    │
│ Cost (Phase 3)    │  $$$   │  $$    │  N/A   │  $$$   │  $$    │  $     │  $$   │
│ Setup complexity  │  Easy  │  Easy  │  Easy  │  Medium│  Medium│  Hard  │  Hard │
│ Production ready  │  ✅    │  ✅    │  ❌    │  ✅    │  ✅    │  ❌    │  ✅   │
│ Startup friendly  │  ✅    │  ✅    │  ✅    │  ⚠️    │  ✅    │  ❌    │  ⚠️  │
├───────────────────┼────────┼────────┼────────┼────────┼────────┼────────┼────────┤
│ OVERALL RATING    │ ★★★★★  │ ★★★★  │ ★★★   │ ★★★★  │ ★★★★  │  ★★    │ ★★★  │
└───────────────────┴────────┴────────┴────────┴────────┴────────┴────────┴────────┘
```

---

## Our Recommendation — 3-Phase Database Strategy

```
╔══════════════════════════════════════════════════════════════════════╗
║              RECOMMENDED DATABASE STRATEGY                           ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  PHASE 1 — Development & MVP (Months 1–4)                           ║
║  ────────────────────────────────────────                            ║
║  LOCAL: Docker + timescale/timescaledb-ha:pg16  ← for development   ║
║  CLOUD: Aiven Hobbyist Plan ($19/mo)            ← for staging/beta  ║
║                                                                      ║
║  Why Aiven for Phase 1:                                              ║
║  • Cheapest cloud option with TimescaleDB support                   ║
║  • Sydney region → Australian data residency from day 1            ║
║  • Can also host Redis + OpenSearch on same platform                ║
║  • Free $300 credit to start (30 days)                             ║
║  • Upgrade path is easy (click to resize)                           ║
║  Total DB cost: $19–50 AUD/mo                                       ║
║                                                                      ║
║  PHASE 2 — Launch & Growth (Months 5–14)                            ║
║  ────────────────────────────────────────                            ║
║  Migrate to: DigitalOcean Droplet (Sydney)                          ║
║  OR:         TimescaleDB Cloud (Launch plan)                        ║
║                                                                      ║
║  Recommended: DigitalOcean 32GB Memory Droplet + TimescaleDB        ║
║  Why DO over cloud managed:                                          ║
║  • $168/mo for 32GB RAM (TimescaleDB Cloud charges $380/mo)         ║
║  • You save $200+/mo — significant for a startup                   ║
║  • Full control — run exactly what you need                        ║
║  • Sydney datacenter (AUS data residency)                           ║
║  • Automated backups via DO Spaces (S3-compatible)                 ║
║  Total DB cost: ~$200–300 AUD/mo (DB + storage + backup)           ║
║                                                                      ║
║  PHASE 3 — Scale (Months 15+)                                       ║
║  ─────────────────────────────                                       ║
║  Primary DB: AWS EC2 r6g.2xlarge (Sydney) + TimescaleDB             ║
║              + Read replica for analytics                           ║
║  Workers: Hetzner Dedicated (EU/US) for Compute Engine batch jobs  ║
║           (much cheaper compute per dollar, non-latency-sensitive)  ║
║                                                                      ║
║  Why AWS for Phase 3:                                                ║
║  • Deep integration with rest of AWS stack (ECS, S3, SES, SNS)     ║
║  • Reserved instances = 40% cheaper                                 ║
║  • RDS Multi-AZ failover option                                     ║
║  • Enterprise SLA                                                    ║
║  Total DB cost: ~$500–800 AUD/mo                                    ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Step-by-Step: Set Up Aiven (Phase 1 Cloud DB)

```
STEP 1: Create Aiven Account
  → Go to: aiven.io
  → Sign up with Google
  → Get $300 free credit automatically

STEP 2: Create PostgreSQL Service
  → Dashboard → Create Service
  → Service: PostgreSQL
  → Version: 16
  → Cloud provider: AWS
  → Region: ap-southeast-2 (Sydney)
  → Plan: Hobbyist ($19/mo) to start
  → Service name: asx-screener-db

STEP 3: Enable TimescaleDB Extension
  → Service Overview → Databases tab
  → Extensions → Search "timescaledb"
  → Enable → Confirm
  → Also enable: pg_trgm, uuid-ossp, vector (pgvector)

STEP 4: Get Connection Details
  → Service Overview → Connection Information
  → Copy: Host, Port, Username, Password, Database name, CA Certificate
  → Your DATABASE_URL will be:
    postgresql://avnadmin:PASSWORD@HOST.aivencloud.com:PORT/defaultdb
    ?sslmode=require

STEP 5: Connect from Local Machine
  → Download CA certificate from Aiven dashboard
  → Test:
    psql "postgresql://avnadmin:PASS@HOST:PORT/defaultdb?sslmode=require"
    SELECT extname FROM pg_extension WHERE extname = 'timescaledb';
    → Should return: timescaledb ✅

STEP 6: Apply Schema
  → Run SQL from Document 02_Database_Design_LLD.md
  → Verify hypertables created:
    SELECT * FROM timescaledb_information.hypertables;
```

---

## Step-by-Step: Set Up DigitalOcean Droplet (Phase 2)

```
STEP 1: Create DigitalOcean Account
  → digitalocean.com (new account gets $200 free credit)

STEP 2: Create Droplet for Database
  → Droplets → Create Droplet
  → Image: Ubuntu 24.04 LTS
  → Size: General Purpose → 32GB / 8 vCPUs / 640GB SSD ($168/mo)
         (start with 16GB / $84/mo and upgrade as needed)
  → Region: Sydney (SYD1 or SYD2)
  → Add SSH key (your public key)
  → Hostname: asx-screener-db-prod
  → Enable: Backups (+20% of droplet price = $34/mo for 32GB)
  → Create Droplet

STEP 3: Configure Firewall
  → DigitalOcean → Networking → Firewalls → Create
  → Inbound rules:
    - SSH (port 22): Your IP only
    - PostgreSQL (port 5432): Your API server IP only
    - NO public internet access to port 5432 (ever)
  → Apply to: asx-screener-db-prod

STEP 4: SSH into Server and Install PostgreSQL 16 + TimescaleDB
  ssh root@YOUR_DROPLET_IP

  # Add PostgreSQL 16 repository
  sudo apt install -y curl ca-certificates
  sudo install -d /usr/share/postgresql-common/pgdg
  curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
       --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
  sh -c 'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
       https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > \
       /etc/apt/sources.list.d/pgdg.list'
  sudo apt update
  sudo apt install -y postgresql-16

  # Add TimescaleDB repository
  echo "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -cs) main" | \
       sudo tee /etc/apt/sources.list.d/timescaledb.list
  wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo apt-key add -
  sudo apt update
  sudo apt install -y timescaledb-2-postgresql-16

  # Run TimescaleDB tuning (auto-configures for your hardware)
  sudo timescaledb-tune --quiet --yes

  # Install pgvector
  sudo apt install -y postgresql-16-pgvector

  # Restart PostgreSQL
  sudo systemctl restart postgresql

STEP 5: Configure PostgreSQL
  sudo -u postgres psql

  -- Create database and user
  CREATE DATABASE asx_screener;
  CREATE USER asx_admin WITH ENCRYPTED PASSWORD 'your_secure_password';
  GRANT ALL PRIVILEGES ON DATABASE asx_screener TO asx_admin;
  \q

  -- Apply schema
  psql -U asx_admin -d asx_screener -f 01_market.sql

STEP 6: Set Up Automated Backups to S3
  pip install boto3
  # Create backup script that runs nightly via cron:
  # pg_dump asx_screener | gzip | aws s3 cp - s3://bucket/backup-$(date +%Y%m%d).gz
  # (script included in infra/scripts/backup.sh)
```

---

## Physical Server: Should You Use It?

```
┌─────────────────────────────────────────────────────────────────────┐
│  VERDICT ON PHYSICAL SERVER                                          │
│                                                                      │
│  Home/Office Server:   ❌ DO NOT USE for production                 │
│                            Acceptable for development only          │
│                            Too risky for paying customers            │
│                                                                      │
│  Colocation:           ⚠️ Only if you have strong sysadmin skills   │
│                            and want data sovereignty above all else  │
│                            Still more work than cloud for less value │
│                                                                      │
│  Dedicated Bare Metal: ✅ Good for one specific use case:            │
│    Hetzner EX44         The Compute Engine batch jobs (Celery/       │
│    64GB RAM, $80/mo     Airflow workers) don't need to be in        │
│                         Australia — they just crunch numbers.        │
│                         Hetzner gives you 64GB for $80/mo vs        │
│                         AWS r6g.2xlarge = 64GB for $490/mo.         │
│                         This is a 6× cost saving on workers!        │
│                                                                      │
│  Summary:                                                            │
│  • Database: Cloud (Aiven → DigitalOcean → AWS)                     │
│  • Compute workers: Hetzner dedicated (massive cost saving)         │
│  • Web/API servers: Cloud (Vercel + Railway → AWS ECS)              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Cost Comparison Over Time

```
                   Phase 1      Phase 2      Phase 3
                   (Dev, 4mo)   (Launch)     (Scale)
                   ─────────    ─────────    ─────────
TimescaleDB Cloud  $95/mo       $190/mo      $380/mo
Aiven              $19/mo       $48/mo       $186/mo
DigitalOcean       $24/mo       $84/mo       $168/mo    ← Best value
AWS EC2 (r6g)      $50/mo       $250/mo      $490/mo
Physical (colo)    $600 setup   $400/mo      $400/mo    ← Expensive+risky
Hetzner dedicated  $80/mo       $80/mo       $160/mo    ← Best for workers

RECOMMENDED COMBINATION:
  Phase 1: Aiven ($19) + local Docker          = $19/mo
  Phase 2: DO Droplet ($168) + Hetzner ($80)   = $248/mo
  Phase 3: AWS EC2 ($490) + Hetzner ($160)     = $650/mo
```

---

## Final Recommendation Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│  FINAL RECOMMENDATION                                                │
│                                                                      │
│  DATABASE:    Aiven (Phase 1) → DigitalOcean (Phase 2) → AWS (Ph3) │
│  PLATFORM:    Cloud — NOT physical for the database                  │
│  WORKERS:     Hetzner dedicated bare metal (Phase 2+)               │
│  FRONTEND:    Vercel (always — free + best Next.js support)         │
│  DATA REGION: Always Sydney (ap-southeast-2) — AUS data residency  │
│                                                                      │
│  START TODAY:                                                        │
│  1. Create Aiven account → aiven.io                                 │
│  2. Create PostgreSQL 16 service, Sydney region, enable TimescaleDB │
│  3. Get connection string → add to .env                             │
│  4. Run docker compose up (local dev against Aiven cloud DB)        │
│  5. Apply schema from Document 02                                    │
│  ✅ You have a production-grade TimescaleDB in Sydney in < 30 min   │
└─────────────────────────────────────────────────────────────────────┘
```
