# A bind parameter followed by `::` is two parameters, not one and a cast

**Found** 24 October 2026, in the production log, while confirming the
v11.2.29 screener fixes had taken.
**Fixed in** v11.2.30.
**Blast radius** every announcement notification, every anomaly alert
e-mail, and every unsubscribe audit-log write — all of them raising before
they could record anything.

## What was served

```
asyncpg.exceptions.PostgresSyntaxError: syntax error at or near ":"
  announcement_worker.py:375   _notify_subscribers
  notification_service.py:210  send_announcement_notification
  notification_service.py:38   _log_notification
```

Nightly. Not intermittent, not load-dependent: the statement could never
have executed.

## Why

```sql
VALUES (:uid, :channel, :type, :subject, :recipient,
        :status, :error, :meta::jsonb, :attempts, ...)
```

SQLAlchemy's `text()` finds bind parameters by matching a colon followed by
a word. Given `:meta::jsonb` it takes `:meta`; of the two colons left, the
first is followed by a colon and does not match, and **the second is
followed by `jsonb`, which it takes as a second bind parameter.** Nothing
supplies `jsonb`, so the statement reaches Postgres with an unfilled
placeholder and the parser stops at the colon.

Verified against the library rather than asserted:
`text("... :meta::jsonb ...")._bindparams` contains `jsonb`.

## The convention was already right

Three occurrences existed. The rest of the codebase writes
`CAST(:x AS jsonb)`, which has no second colon and cannot be misparsed —
including, in `anomaly_alert_worker.py`, on the line **immediately above**
the broken one:

```sql
VALUES (CAST(:uid AS uuid), 'email', 'anomaly_alert', :subject, :email,
        :status, :meta::jsonb, 1, ...)
         ^^^^^^^^^^^^^^^^^^^^ correct      ^^^^^^^^^^^^ broken
```

So this is not a missing convention. It is three sites that departed from
one, in a construct where the departure is invisible to review: `::jsonb`
is correct Postgres, correct in a psycopg `%s` query, and correct in every
other place a developer has seen it. It is wrong only inside `text()`, and
only because of how `text()` scans for colons.

## Why nothing caught it

- `python -m py_compile` passes: the string is a valid string.
- The test suite has 86 files and **none of them issues an HTTP request or
  executes these statements**, so no test ever handed this SQL to
  SQLAlchemy. This is the same gap that let the v11.2.27 route-binding
  regression ship and be reported as 82 tests passing.
- The failure is in a background worker. Nobody is watching a response code
  when a nightly job raises.

## The guard

`backend/tests/test_no_bindparam_followed_by_cast.py`, four properties:

1. **Population, not a list.** No `:name::type` anywhere under `app/`,
   `compute/`, `scripts/` — so a fourth site added tomorrow fails the gate
   rather than waiting for a customer.
2. **The mechanism, behaviourally.** SQLAlchemy itself is asserted to
   extract `jsonb` from the broken form and exactly `{meta, attempts}` from
   the fixed one. If a future version changes that, the test says so
   instead of quietly protecting nothing.
3. **End-to-end on the shipped source.** Every `text()` literal in the
   three repaired files is parsed out of the file by AST and handed to
   `text()`; none may bind a SQL type name.
4. **A mutation control**, and a false-positive control over forms that
   must not be flagged (`SELECT a::text`, `INTERVAL '1 day'`).

## What this does not fix

Found in the same log and **not** addressed here: two workers query
`np.email_enabled`, and `users.notification_preferences` has no such
column — it has `alerts_email`, `announcements_email`,
`portfolio_weekly_email`. Which flag governs which notification is a
product decision, not a rename, so it is left for a separate change.

## Rule

A construct that is correct in four contexts and wrong in the fifth will
not be caught by reading it. The textual guard is cheap and belongs in the
gate; but the property is behavioural, and the only thing that actually
establishes it is handing the shipped SQL to the library that parses it.
