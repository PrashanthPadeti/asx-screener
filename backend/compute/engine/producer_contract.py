"""
A producer that obtained nothing did not succeed
================================================
`index_prices` and `fund_prices` ran on 3, 4, 5 and 6 October 2026, reported
terminal `success` in `ops.job_executions` every time, and wrote zero rows.
Their published output has not advanced past 1 October. `fund_prices` spent
about ten hours of execution across those four days producing nothing.

The mechanism was a single line repeated in both:

    df = await asyncio.to_thread(fetch_..., ticker, start, end)
    if df is None:
        continue

`None` was returned both when the source had nothing for a ticker and when the
source refused the request. Every ticker refused, every iteration continued,
the loop ended, the coroutine returned normally, and the instrumentation
recorded success. Nothing lied; nobody asked.

This module makes the absence representable, which is the same rule the
governed metrics already follow one layer up: a value that could not be
obtained is reported as unobtained, with a cause, rather than passed through
as an ordinary result.

What is deliberately NOT decided here
-------------------------------------
Whether a partial run should fail. 9 of 10 indices is a judgement about
completeness that needs its own justification and its own evidence, and
picking 90% today would be an arbitrary number wearing a contract's clothes.
The contract below is the part that is already proven: a non-empty expected
population yielding zero usable observations is a failure. Partial results are
preserved, counted and reported, and remain a success until someone defines
the threshold on the merits.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class SourceRefused(Exception):
    """The upstream declined to serve us — rate limit, quota, block.

    Distinct from "the source has no data for this symbol", which is an
    ordinary empty result. Conflating the two is the defect this module
    exists to prevent: one means our request failed, the other means the
    answer is legitimately nothing.
    """

    def __init__(self, ticker: str, detail: str = ""):
        self.ticker = ticker
        self.detail = detail
        super().__init__(f"{ticker}: source refused the request"
                         + (f" — {detail}" if detail else ""))


class ProducerFailure(RuntimeError):
    """Raised at the end of a run that obtained nothing.

    Raised rather than returned so that APScheduler and
    `app.core.job_instrumentation.instrumented` both see a failure. The
    wrapper records whatever the job raises and re-raises it unchanged, so a
    return value would be invisible to `ops.job_executions` — the job would
    go on reporting success, which is the whole defect.
    """


@dataclass
class ProducerTally:
    """What a producer actually obtained, counted as it goes.

    Kept as explicit counters rather than inferred from rows written: a run
    that writes 0 rows because every ticker was refused and a run that writes
    0 rows because the market was closed are different events, and the cause
    is what distinguishes them.
    """

    producer: str
    expected: int = 0
    usable: int = 0
    refused: int = 0
    empty: int = 0
    rows: int = 0
    refusals: list[str] = field(default_factory=list)

    def refusal(self, ticker: str) -> None:
        self.refused += 1
        if len(self.refusals) < 5:
            self.refusals.append(ticker)

    def nothing_available(self) -> None:
        self.empty += 1

    def obtained(self, rows: int) -> None:
        self.usable += 1
        self.rows += rows

    @property
    def summary(self) -> str:
        return (f"{self.producer}: {self.usable}/{self.expected} obtained, "
                f"{self.refused} refused, {self.empty} empty, "
                f"{self.rows} rows")

    def verify(self) -> None:
        """Enforce the contract. Call at the end of every run.

        expected > 0 AND usable == 0  ->  ProducerFailure

        The expected population comes from the producer's own ticker list, so
        a run over an empty population is vacuous rather than failed — there
        is nothing to be stale about, and raising there would make an empty
        configuration look like an outage.
        """
        if self.expected == 0:
            return
        if self.usable > 0:
            return

        if self.refused:
            sample = ", ".join(self.refusals)
            more = "" if self.refused <= len(self.refusals) else ", …"
            cause = (f"source_refused — {self.refused} of {self.expected} "
                     f"requests declined ({sample}{more})")
        else:
            cause = (f"no_observations — all {self.expected} requests "
                     f"returned empty")

        raise ProducerFailure(
            f"{self.producer} obtained 0 usable results from "
            f"{self.expected} expected: {cause}")
