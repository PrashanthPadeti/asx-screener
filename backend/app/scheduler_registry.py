"""
Scheduled job registration — one declaration, two possible hosts
===============================================================
Every `scheduler.add_job(...)` for this system lives here, extracted
verbatim from app/main.py's lifespan in v11.2.43 with NO behaviour change.

Why it moved: the 18 jobs run inside the uvicorn process that serves
customers, so a job that blocks the event loop or leaks memory degrades
stock screening, the market overview and the company pages -- the three
things the product exists to provide. v11.2.44 adds a worker service that
calls this same function, and the API is then started with
SCHEDULERS_ENABLED=false.

One declaration, deliberately. If the API and the worker each kept their
own list, they would drift, and the drift would show up as a job running
twice -- duplicate emails, duplicate writes, duplicate compute runs --
or not at all. This codebase has four operator vocabularies as the
standing argument against a second copy of anything.

The flag guards here are load-bearing and are checked by
test_alert_isolation and test_watchlist_digest_isolation, which parse THIS
file. When the registrations moved, those guards moved with them: a guard
that cannot find its subject protects nothing, and the alert guard spent
eight releases in exactly that state after jobs were wrapped in
instrumented().
"""


def register_jobs(scheduler, settings, logger) -> None:
    """Register every scheduled job on `scheduler`.

    Takes settings and logger as arguments rather than importing them, so
    the worker process can supply its own without this module reaching back
    into the API's module graph.
    """
    # instrumented() was a module-level import in main.py, so it was NOT
    # inside the block that moved. Without it every add_job call here is
    # an undefined name and the process fails to start -- caught by the
    # lint gate (F821) before any deploy.
    from app.core.job_instrumentation import instrumented
    from apscheduler.triggers.cron import CronTrigger
    from app.workers.alert_worker import check_alerts
    from app.workers.portfolio_worker import check_portfolio_thresholds, send_weekly_portfolio_summaries
    from app.workers.announcement_worker import fetch_announcements
    from app.workers.watchlist_digest_worker import send_watchlist_digests
    from app.workers.index_prices_worker import compute_index_prices
    from app.workers.fund_prices_worker import compute_fund_prices
    from app.workers.global_markets_worker import compute_global_markets
    from app.workers.commodities_worker import compute_commodities
    from app.workers.market_snapshot_worker import run_market_snapshot
    from app.workers.asx_indices_worker import run_asx_indices
    from app.workers.short_positions_worker import run_short_positions
    from app.workers.anomaly_worker import run_anomaly_detect
    from app.workers.top5_strategy_worker import run_top5_strategy
    from app.workers.asx_companies_worker import sync_asx_companies
    from app.workers.anomaly_alert_worker import send_anomaly_alerts
    from app.workers.capital_raise_worker import scan_capital_raises
    from app.workers.cleanup_worker import purge_expired_sessions, run_data_deletion
    from app.workers.mining_reit_worker import sync_mining_reit_metrics

    scheduler.add_job(instrumented("alert_checker", check_alerts), trigger="interval", minutes=15,
                      id="alert_checker", replace_existing=True)

    # Portfolio threshold alerts — every 30 min
    scheduler.add_job(instrumented("portfolio_threshold_checker", check_portfolio_thresholds), trigger="interval", minutes=30,
                      id="portfolio_threshold_checker", replace_existing=True)

    # Weekly portfolio summary — Monday 8am AEST
    scheduler.add_job(instrumented("weekly_portfolio_summary", send_weekly_portfolio_summaries),
                      CronTrigger(day_of_week="mon", hour=8, minute=0,
                                  timezone="Australia/Sydney"),
                      id="weekly_portfolio_summary", replace_existing=True)

    # ASX announcements — once daily at 7:10pm AEST, after market close.
    #
    # Was every 10 minutes. At 200 symbols per run and 5 EODHD calls per news
    # request, that billed 144,000 calls a day against a 100,000 account limit —
    # the entire quota consumed by one job, starving price and fundamentals
    # ingestion and the US Screener that shares the key. Daily costs 1,000.
    #
    # ASX Screener is an end-of-day product: nothing here needs intraday polling.
    scheduler.add_job(instrumented("announcement_fetcher", fetch_announcements),
                      CronTrigger(hour=19, minute=10, timezone="Australia/Sydney"),
                      id="announcement_fetcher", replace_existing=True)

    # Watchlist daily digest — 7:30am AEST.
    #
    # Registered ONLY when deliberately enabled. This has never sent: it was
    # written against a column that does not exist and raised on every run
    # from 6 May 2026 until v11.2.30 repaired the query. Fixing the column
    # would otherwise have launched a daily email to every user with a
    # watchlist, governed by a preference labelled "weekly", without anyone
    # choosing to launch it.
    if settings.WATCHLIST_DIGEST_ENABLED:
        scheduler.add_job(instrumented("watchlist_digest", send_watchlist_digests),
                          CronTrigger(hour=7, minute=30, timezone="Australia/Sydney"),
                          id="watchlist_digest", replace_existing=True)
        logger.warning(
            "WATCHLIST DIGEST EMAILS ARE ENABLED — a daily digest will be "
            "sent at 07:30 AEST to every user with a watchlist. This feature "
            "has never sent before; confirm the opt-in preference exists and "
            "the first send is intended.")
    else:
        logger.info(
            "Watchlist digest disabled (WATCHLIST_DIGEST_ENABLED is off). "
            "It has never sent; enabling it is a first launch, not a "
            "restoration.")

    # ASX index prices — daily at 5:30pm AEST (30 min after market close)
    scheduler.add_job(instrumented("index_prices", compute_index_prices),
                      CronTrigger(hour=17, minute=30, timezone="Australia/Sydney"),
                      id="index_prices", replace_existing=True)

    # ASX ETF/fund prices — daily at 5:35pm AEST
    scheduler.add_job(instrumented("fund_prices", compute_fund_prices),
                      CronTrigger(hour=17, minute=35, timezone="Australia/Sydney"),
                      id="fund_prices", replace_existing=True)

    # Global market indices + AUD FX — daily at 5:40pm AEST
    scheduler.add_job(instrumented("global_markets", compute_global_markets),
                      CronTrigger(hour=17, minute=40, timezone="Australia/Sydney"),
                      id="global_markets", replace_existing=True)

    # Commodity prices — daily at 5:45pm AEST
    scheduler.add_job(instrumented("commodities", compute_commodities),
                      CronTrigger(hour=17, minute=45, timezone="Australia/Sydney"),
                      id="commodities", replace_existing=True)

    # ASX index constituent flags (is_asx200/300) — daily at 5:50pm AEST
    scheduler.add_job(instrumented("asx_indices", run_asx_indices),
                      CronTrigger(hour=17, minute=50, timezone="Australia/Sydney"),
                      id="asx_indices", replace_existing=True)

    # ASIC short positions — daily at 8:05pm AEST
    # Moved from 6:30pm: the daily_pipeline (cron 6:30pm) processes short positions in
    # steps 2/4/6; running APScheduler at the same time caused simultaneous writes to
    # staging_au.short_positions / market.short_positions.  8:05pm is well after the
    # pipeline finishes (~7:30-7:40pm) and still covers ASIC's ~6pm publication lag.
    scheduler.add_job(instrumented("short_positions", run_short_positions),
                      CronTrigger(hour=20, minute=5, timezone="Australia/Sydney"),
                      id="short_positions", replace_existing=True)

    # Market snapshot (ASX200/300, movers, shorted) — daily at 7:50pm AEST
    # Moved from 6:45pm: at 6:45pm the pipeline's compute engines (steps 7-10) and
    # universe build (step 13) had not yet finished, so the snapshot read stale
    # period_metrics and an incomplete screener.universe.  7:50pm gives a 10-15 min
    # buffer after the pipeline's own step 14 snapshot (~7:30-7:40pm) and acts as a
    # safety-net rerun with fully-settled data.
    scheduler.add_job(instrumented("market_snapshot", run_market_snapshot),
                      CronTrigger(hour=19, minute=50, timezone="Australia/Sydney"),
                      id="market_snapshot", replace_existing=True)

    # Anomaly detection — daily at 8:20pm AEST (after snapshot safety-net at 7:50pm)
    # Moved from 7:00pm: anomaly detection reads mover_snapshots; running at 7:00pm
    # meant the pipeline step 14 snapshot (~7:30pm) had not yet written fresh data.
    scheduler.add_job(instrumented("anomaly_detect", run_anomaly_detect),
                      CronTrigger(hour=20, minute=20, timezone="Australia/Sydney"),
                      id="anomaly_detect", replace_existing=True)

    # Anomaly alert emails — daily at 8:35pm AEST (15 min after anomaly detection)
    #
    # Registered ONLY when deliberately enabled. This is the outbound path for
    # anomaly flags, and the active anomaly set is known to contain
    # defect-derived ones until the detector applicability repair and
    # re-detection sequence complete (P0-A-7).
    #
    # The control has to live here rather than in the freeze script, because
    # the freeze script's job is to stop schedulers and its thaw restores them
    # all. Anything relying on `thaw` remembering to leave one job out is a
    # reminder, not an exclusion -- and it would fail for anyone who restarts
    # the service by any other route.
    if settings.ANOMALY_ALERTS_ENABLED:
        scheduler.add_job(instrumented("anomaly_alerts", send_anomaly_alerts),
                          CronTrigger(hour=20, minute=35, timezone="Australia/Sydney"),
                          id="anomaly_alerts", replace_existing=True)
        logger.warning(
            "ANOMALY ALERT EMAILS ARE ENABLED — outbound anomaly alerts will "
            "be sent at 20:35 AEST. This must only be on once the detector's "
            "re-detection sequence has run and the active flag set has been "
            "verified free of defect-derived anomalies.")
    else:
        logger.info(
            "Anomaly alert emails disabled (ANOMALY_ALERTS_ENABLED is off). "
            "Detection still runs and records flags; nothing is emailed.")

    # Capital raise scanner — daily at 7:30am AEST (after announcement fetch settles)
    scheduler.add_job(instrumented("capital_raise_scan", scan_capital_raises),
                      CronTrigger(hour=7, minute=30, timezone="Australia/Sydney"),
                      id="capital_raise_scan", replace_existing=True)

    # Mining & REIT metrics sync — weekly Sunday at 7:00am AEST
    scheduler.add_job(instrumented("mining_reit_metrics", sync_mining_reit_metrics),
                      CronTrigger(day_of_week="sun", hour=7, minute=0, timezone="Australia/Sydney"),
                      id="mining_reit_metrics", replace_existing=True)

    # Top 5 monthly picks — 2nd of each month at 8pm AEST (after universe + composite scores settle)
    scheduler.add_job(instrumented("top5_strategy", run_top5_strategy),
                      CronTrigger(day=2, hour=20, minute=0, timezone="Australia/Sydney"),
                      id="top5_strategy", replace_existing=True)

    # Nightly cleanup — 2:00am AEST (low traffic window)
    scheduler.add_job(instrumented("session_cleanup", purge_expired_sessions),
                      CronTrigger(hour=2, minute=0, timezone="Australia/Sydney"),
                      id="session_cleanup", replace_existing=True)

    # Premium data deletion — 2:15am AEST (after session cleanup)
    # Removes portfolios/alerts for cancelled users whose 12-month window has passed
    scheduler.add_job(instrumented("data_deletion", run_data_deletion),
                      CronTrigger(hour=2, minute=15, timezone="Australia/Sydney"),
                      id="data_deletion", replace_existing=True)

    # ASX companies list sync — daily at 6:00am AEST (before universe build)
    scheduler.add_job(instrumented("asx_companies", sync_asx_companies),
                      CronTrigger(hour=6, minute=0, timezone="Australia/Sydney"),
                      id="asx_companies", replace_existing=True)
