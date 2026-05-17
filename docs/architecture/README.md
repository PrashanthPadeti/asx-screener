# Data Platform Architecture — Document Index

This directory contains the authoritative architecture standards for all projects built
on the shared data platform. Every project (ASX Screener, India Nifty Screener,
US Screener, Charting, and any future projects) must follow these standards.

## Documents

| # | Document | Purpose |
|---|---|---|
| 01 | [Platform Overview](01_platform_overview.md) | Full architecture, all 4 projects, layer definitions |
| 02 | [Bronze Layer — Raw Zone Guide](02_bronze_layer_guide.md) | How to read/write the shared data lake |
| 03 | [Naming Conventions](03_naming_conventions.md) | Schema, table, column, file, and code naming rules |
| 04 | [Starting a New Project](04_new_project_checklist.md) | Step-by-step checklist for bootstrapping a new project |
| 05 | [Pipeline Development Standards](05_pipeline_standards.md) | How to write ingestion, transform, and compute jobs |

## Quick Reference

### The One Rule
> **All projects share the Bronze Raw Zone. After the Raw Zone, every project is fully independent.**
> Changes in one project must never affect another.

### Project → Schema Mapping

| Project | Staging | Market Transform | Financials | Application |
|---|---|---|---|---|
| ASX Screener | `stg_au.*` | `mkt_au.*` | `fin_au.*` | `screener_au.*` |
| India Nifty Screener | `stg_in.*` | `mkt_in.*` | `fin_in.*` | `screener_in.*` |
| US Screener | `stg_us.*` | `mkt_us.*` | `fin_us.*` | `screener_us.*` |
| Charting | `stg_charts.*` | `charts_mkt.*` | — | `charts.*` |
| Shared Infra | — | — | — | `users.*` `notifications.*` `ai.*` |

### Raw Zone Path

```
/opt/data-lake/raw/eodhd/exchange=AU/       ← ASX
/opt/data-lake/raw/eodhd/exchange=NSE/      ← India NSE
/opt/data-lake/raw/eodhd/exchange=BSE/      ← India BSE
/opt/data-lake/raw/eodhd/exchange=NYSE/     ← US NYSE
/opt/data-lake/raw/eodhd/exchange=NASDAQ/   ← US NASDAQ
/opt/data-lake/raw/asic/                    ← ASX short positions
/opt/data-lake/raw/nse-india/               ← India NSE direct feeds
/opt/data-lake/raw/sec/                     ← US SEC EDGAR
/opt/data-lake/raw/finra/                   ← US FINRA short interest
```

## Ownership

- **Bronze Layer / Data Lake**: Platform team (shared)
- **ASX Screener**: ASX Screener team
- **India Nifty Screener**: India Screener team
- **US Screener**: US Screener team
- **Charting**: Charting team

Questions about the platform architecture → update these docs and notify all teams.
