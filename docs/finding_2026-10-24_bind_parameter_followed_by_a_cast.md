# A bind parameter followed by `::` is never substituted at all

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

Measured against SQLAlchemy 2.0.36 — the version in `asx-venv`:

```
text("INSERT INTO t (a,b) VALUES (:meta::jsonb, :attempts)")
  binds    -> ['attempts', 'met']
  compiled -> INSERT INTO t (a,b) VALUES (:meta::jsonb, $1)
```

Two things go wrong at once.

**The cast expression is never substituted.** `:attempts` became `$1`.
`:meta::jsonb` was left in the SQL exactly as written, so Postgres received
a literal colon and stopped at it. That is the reported syntax error.

**A truncated phantom parameter is registered.** Not `meta` — `met`. The
scanner stops one character short of the `::` and keeps the shortened name.
It is registered as a bind and then never rendered, so nothing supplies it
and nothing raises about it. `:uid::uuid` registers `ui` the same way.

The correct form substitutes cleanly:

```
text("... VALUES (CAST(:meta AS jsonb), :attempts)")
  binds    -> ['attempts', 'meta']
  compiled -> ... VALUES (CAST($1 AS jsonb), $2)
```

### A correction, recorded because it nearly shipped

The first version of this document and of the commit message said
`:meta::jsonb` registers `jsonb` as a *second* bind parameter. That is
wrong; it registers `met`. The guard written around that wrong story
rejected bind names that are SQL type names — and `met` is not one, so
**the guard passed the live defect.** It was only caught because a separate
test asserted the mechanism against the library itself and failed.

A guard derived from an explanation is only as good as the explanation.
This one is now derived from a measurement.

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

`backend/tests/test_no_bindparam_followed_by_cast.py`.

The load-bearing one is a property, not a pattern:

> **Every bind parameter a statement registers must appear as a `$n`
> placeholder in the compiled SQL.**

Applied by AST to every `text()` literal under `app/`, `compute/` and
`scripts/`, each compiled against the asyncpg dialect. The broken form
registers two and renders one, so it fails. This holds whatever the
scanner's regex turns out to be, and it catches *any* construct that
defeats substitution — not only `::`, and not only the spellings I thought
to enumerate.

Supporting it:

- A **mutation control** on the exact statement from the traceback, which
  fails loudly if SQLAlchemy's behaviour ever changes.
- An assertion that the phantom is `met` and `ui` — pinning the detail I
  got wrong so it cannot quietly revert to the wrong story.
- The cheap **textual tripwire** (no `:name::type` anywhere in the tree),
  kept because it needs no dialect and names the offending line directly,
  with a false-positive control over `SELECT a::text` and
  `INTERVAL '1 day'`.
- A **coverage floor**: the AST pass must compile at least 20 statements,
  so the property cannot silently narrow to nothing.

## What this does not fix

Found in the same log and **not** addressed here: two workers query
`np.email_enabled`, and `users.notification_preferences` has no such
column — it has `alerts_email`, `announcements_email`,
`portfolio_weekly_email`. Which flag governs which notification is a
product decision, not a rename, so it is left for a separate change.

## Rule

A construct that is correct in four contexts and wrong in the fifth will
not be caught by reading it — and neither will it be caught by a guard
built from your explanation of why it is wrong. The explanation here was
wrong, and the guard built on it passed the live defect.

The only thing that established the property was handing the shipped SQL to
the library that parses it and comparing what went in against what came
out. Measure the mechanism, then derive the guard from the measurement.
