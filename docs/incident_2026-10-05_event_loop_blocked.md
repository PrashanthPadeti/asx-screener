# 5 October 2026 — the API slept through its own outage

Cloudflare 504 from ~06:36 to 07:11 UTC. Customers could not load the site or
log in. Thirty-five minutes, and it had about 1.8 hours still to run when the
service was restarted.

## What it looked like

    service   active (running) 2h31m, listening on :8000
    health    http=000, timed out at 10s
    load      0.00, 0.00, 0.00
    memory    288M of 3915M

The process was not busy, not short of memory, not crashed. It was **asleep**.

## Cause

`AsyncIOScheduler` runs coroutine jobs **on the event loop**.
`compute_fund_prices` is `async def`. Its loop did:

    time.sleep(2)                       # between tickers
    fetch_fund_data(...)                # synchronous, and inside it:
        time.sleep(30/60/90)            # backoff on rate limit

Yahoo rate-limited every request, so each of 47 funds cost 182 seconds of
blocking sleep. While a coroutine blocks the loop the process answers nothing
— not `/health`, not login, not a single request.

Trigger: `CronTrigger(hour=17, minute=35, timezone="Australia/Sydney")`
= **06:35 UTC**, matching the start exactly.

Worst case was a **daily 2.4-hour outage** whenever Yahoo rate-limits.

## Fix

The blocking work moves off the loop; it is not deleted.

    await asyncio.sleep(2)
    df = await asyncio.to_thread(fetch_fund_data, ticker, start, end)

`fetch_fund_data` stays synchronous — yfinance is — and keeps its 30/60/90
backoff. Running it through `to_thread` puts that sleeping on a worker thread.
The job still takes as long; the API stays up.

`tests/test_no_blocking_sleep_on_the_event_loop.py` scans `app/workers`,
`compute/engine` and `app/api` with the **AST**, flagging blocking calls
lexically inside a coroutine while permitting them in nested sync functions —
because holding blocking work in a sync function is the remedy, not the bug. A
guard that forbade both would push people to delete the backoff instead of
moving it. Mutation-controlled: restoring `time.sleep(2)` fails it.

## Second outage in the same risk class — not the same proven mechanism

2 October: ~40 minutes of unavailability, with `announcement_fetcher`
co-located in the API process making hundreds of serial outbound calls. That
established co-location as an availability **risk**; which resource was
actually starved was never proven, only inferred from log lines that happened
to be present.

Today's mechanism **is** proven: blocking calls inside an async scheduler
coroutine froze the event loop, with `load 0.00` and a listening socket ruling
out CPU, memory and crash.

So: second outage in the same architectural risk class — long external work
co-located with the serving process — and the first with a demonstrated
mechanism. The 2 October remediation, moving that work out of the API process,
was recorded and not done.

Fixing the blocking call removes **this** outage. It does not remove the
design: 19 jobs still run inside the API process, several of them outbound-call
producers (`global_markets` 17:40, `commodities`, `asx_indices`,
`index_prices`). Today they were queued behind `fund_prices` and may not have
run at all.

## Two things that were luck, not design

**`misfire_grace_time: 3600`.** The restart at 07:11 was 36 minutes after the
06:35 trigger, inside the grace window. The job could have re-fired
immediately into the same outage. It did not — `coalesce` plus the in-progress
run advancing the next fire time is the likely reason. That was not verified
beforehand.

**Nothing detected it.** No alert, no page. It was found because a human tried
to log in. The external uptime sentinel added after 2 October runs on GitHub
Actions at `17,47 * * * *` and should have caught a 35-minute outage — why it
did not is unexamined and belongs in its own investigation.

## Not in scope

The retry policy itself. 47 tickers × 3 attempts against a source that
rate-limits every call achieves nothing and costs 2.4 hours; whether the
backoff should give up sooner, or the source should change, is a separate
question from whether it may block the API while it tries.
