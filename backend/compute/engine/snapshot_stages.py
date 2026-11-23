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

# The only import this module has, and still nothing third-party: it keeps
# `str | None` annotations evaluable on whatever Python the server happens to
# run, so the properties below stay assertable on any machine.
from __future__ import annotations

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


#: The four buckets every constituent of an index falls into, exactly one
#: each. Named here rather than inferred from the SQL so the partition can be
#: asserted without a database -- see `index_partition_gap`.
INDEX_PARTITION = ("gainers", "losers", "unchanged", "no_return")

#: How much of an index may be unattributed before its aggregate stops being
#: an aggregate OF that index.
#:
#: `AVG(return_1w)` skips NULLs, so an index with 40 of 300 constituents
#: missing publishes the average of 260 under a label that says 300. One or two
#: companies genuinely without a week of prices (a fresh listing, a long
#: suspension) is a gap to record; a large fraction is not a gap at all -- it
#: means the universe was mid-rebuild, or the price pipeline failed upstream,
#: and the honest output is no snapshot rather than a confident number over
#: whatever happened to be present. 2% is a declared bound, so a run that
#: crosses it says so by name instead of averaging quietly.
MAX_UNATTRIBUTED_FRACTION = 0.02


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


def index_partition_gap(index_code: str, row) -> str | None:
    """Do the four buckets account for every constituent? Message if not.

    `stock_count` is the whole index; gainers, losers, unchanged and no_return
    are meant to partition it. Nothing enforced that, and the arithmetic is
    where this family of defects shows up first: when `unchanged` counted
    `return_1w = 0 OR return_1w IS NULL`, the four numbers still summed
    correctly -- because one of them was absorbing another's rows. Only once
    `no_return` is counted and stored separately does the sum become a check
    with any power.

    It catches the realistic next mistake too: a `return_1w` of NaN satisfies
    none of `> 0`, `< 0`, `= 0` or `IS NULL`, so it would vanish from all four
    buckets and the published total would exceed their sum with nothing
    anywhere saying which rows went missing.

    Returns None when the partition holds.
    """
    total = row["stock_count"] or 0
    parts = {name: (row[name] or 0) for name in INDEX_PARTITION}
    summed = sum(parts.values())
    if summed == total:
        return None
    return (f"{index_code}: the four buckets sum to {summed} but stock_count "
            f"is {total} ("
            + ", ".join(f"{k}={v}" for k, v in parts.items())
            + f"). {abs(total - summed)} constituent(s) are in none of them, "
              f"or in more than one, so the published row does not describe "
              f"the index it names.")


def index_coverage_refusal(index_code: str, row) -> str | None:
    """Is enough of the index attributed for its aggregate to mean anything?

    Separate from `index_partition_gap` because they fail for different
    reasons and want different responses. A partition gap is a bug in this
    code. Poor coverage is a true statement about the inputs, and the run
    refuses because `AVG(return_1w)` would publish the average of the
    attributed subset under the index's own name.

    Returns None when coverage is adequate.
    """
    total = row["stock_count"] or 0
    missing = row["no_return"] or 0
    if total <= 0:
        return (f"{index_code}: the index has no active constituents at all, "
                f"so there is nothing to aggregate. This is a universe or "
                f"index-membership failure, not an empty market.")
    fraction = missing / total
    if fraction <= MAX_UNATTRIBUTED_FRACTION:
        return None
    return (f"{index_code}: {missing} of {total} constituents "
            f"({fraction:.1%}) have no return_1w, over the "
            f"{MAX_UNATTRIBUTED_FRACTION:.0%} bound. AVG(return_1w) skips "
            f"them, so publishing would label the average of "
            f"{total - missing} as the return of {total}. At this scale the "
            f"cause is upstream -- a mid-rebuild universe or a failed price "
            f"load -- not a handful of companies without a week of prices.")
