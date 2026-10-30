"""
What a market snapshot run owes, independent of how it talks to a database
==========================================================================
Separated from market_snapshot so the properties here can be asserted without
SQLAlchemy, psycopg2 or a database. That is not tidiness: the condition this
module describes ran in production 127 times and was reported as success every
time, and a test for it that can only execute on one machine is a test that
will be skipped exactly when it matters.

The condition, concretely -- stages 1 and 2 destroyed by a rollback in stage 3,
stages 3 and 4 committed normally:

    {"index": 0, "sector": 0, "movers": 80, "exdiv": 12}
"""

#: Stages that must write rows for a run to be a success. A snapshot that
#: silently produces two of four outputs is the defect: the Market Overview
#: page served 30 May figures until 30 October while the job logged
#: "Committed snapshot" and incremented its heartbeat nightly.
REQUIRED_STAGES = ("index", "sector", "movers")

#: The mover periods the engine wants, and the screener.universe column each
#: needs. `return_1d` has never existed. The engine used to discover that by
#: RUNNING the query and catching the error, which is how a rollback was
#: reached on every single run. Availability is established before any
#: statement executes; a column that cannot exist is a fact, not a failure.
#:
#: return_1d stays listed on purpose. Deleting it would silence the symptom
#: and lose the real gap, which is that a 1-day return is not computed.
RETURN_PERIODS = (("1D", "return_1d"), ("1W", "return_1w"),
                  ("1M", "return_1m"), ("3M", "return_3m"))


class SnapshotIncomplete(RuntimeError):
    """A required stage wrote nothing, so the run is not a success.

    Raised AFTER committing whatever did succeed: the partial data is real,
    already durable, and better than none. What must not survive is the claim
    that the run was clean -- absence of failure is not successful
    maintenance, and an expected output either proves it was published or the
    run says it wasn't.
    """


def incomplete_stages(written: dict) -> list:
    """Required stages that wrote no rows, in declaration order."""
    return [stage for stage in REQUIRED_STAGES if not written.get(stage)]
