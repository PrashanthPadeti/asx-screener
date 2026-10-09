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

#: What happened to one entity. Recorded per entity, never aggregated away.
#:
#: Three different causes produced the identical symptom "this fund has no
#: current price": never requested (8 ETFs absent from a hardcoded list),
#: dead identifier (DIV delisted 2020, PMC renamed to GLS), and the provider
#: refusing the host (yfinance, 9 Oct 2026). A job-level verdict cannot tell
#: them apart, which is how all three coexisted unnoticed for months.
USABLE = "usable"                  # rows written
EMPTY = "empty"                    # provider answered, no data for it
PROVIDER_ERROR = "provider_error"  # transport, HTTP, refusal
EXCLUDED = "excluded"              # deliberately skipped, with a reason

FAILING_OUTCOMES = (EMPTY, PROVIDER_ERROR)


@dataclass(frozen=True)
class EntityOutcome:
    code: str
    outcome: str
    rows: int = 0
    reason: str | None = None

    def __str__(self) -> str:
        base = f"{self.code}: {self.outcome}"
        if self.outcome == USABLE:
            return f"{base} ({self.rows} rows)"
        return f"{base}" + (f" — {self.reason}" if self.reason else "")


@dataclass(frozen=True)
class PopulationReconciliation:
    """The eligible population against the set a producer will actually fetch.

    `fund_prices` took `expected=len(FUNDS)` from the same hardcoded list that
    decides what gets fetched, so dropping an entity dropped `expected` with
    it and the contract could not notice. Eight ETFs served June prices for
    four months inside a job that reported success every day.

    Both directions are findings, and they are different findings:

        eligible - configured  ->  omitted, silently never refreshed
        configured - eligible  ->  stale configuration, fetched forever for
                                   a security that no longer trades

    `eligible` must come from the source of truth (`market.funds` and its
    lifecycle), never from the producer's own list. A population derived from
    the thing it is meant to check cannot disagree with it.
    """

    producer: str
    eligible: frozenset[str]
    configured: frozenset[str]

    @property
    def omitted(self) -> frozenset[str]:
        return frozenset(self.eligible - self.configured)

    @property
    def stale_configured(self) -> frozenset[str]:
        return frozenset(self.configured - self.eligible)

    @property
    def reconciled(self) -> bool:
        return not self.omitted and not self.stale_configured

    @property
    def summary(self) -> str:
        return (f"{self.producer} population: {len(self.eligible)} eligible, "
                f"{len(self.configured)} configured, "
                f"{len(self.omitted)} omitted, "
                f"{len(self.stale_configured)} stale")

    def findings(self) -> list[str]:
        out = []
        if self.omitted:
            out.append(f"omitted from the fetch set, so never refreshed: "
                       f"{', '.join(sorted(self.omitted))}")
        if self.stale_configured:
            out.append(f"configured but not eligible, so fetched for nothing: "
                       f"{', '.join(sorted(self.stale_configured))}")
        return out


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
    outcomes: list[EntityOutcome] = field(default_factory=list)
    population: PopulationReconciliation | None = None

    # ── Per-entity recording ────────────────────────────────────────────────
    # Every method takes the entity code. The counters remain, because "how
    # many" is still the contract in `verify()`, but an aggregate alone cannot
    # answer "which one, and why" — and that is the question DIV and PMC went
    # unanswered on for the producer's entire life, at 45 of 47 passing.

    def refusal(self, code: str, detail: str | None = None) -> None:
        # Record FIRST: _record raises on a duplicate, and a rejected
        # verdict must leave the counters untouched. Incrementing first meant
        # a refused duplicate still moved the totals it was refused for.
        self._record(EntityOutcome(code, PROVIDER_ERROR,
                                   reason=detail or "source refused"))
        self.refused += 1
        if len(self.refusals) < 5:
            self.refusals.append(code)

    def nothing_available(self, code: str) -> None:
        self._record(EntityOutcome(code, EMPTY,
                                   reason="provider returned no data"))
        self.empty += 1

    def obtained(self, code: str, rows: int) -> None:
        self._record(EntityOutcome(code, USABLE, rows=rows))
        self.usable += 1
        self.rows += rows

    def excluded(self, code: str, reason: str) -> None:
        """Deliberately skipped. The reason is required, not optional.

        An exclusion without a recorded reason is indistinguishable from an
        omission, which is the defect this whole change exists to end.

        An exclusion also does NOT settle the population. A code excluded here
        that is eligible-but-unconfigured still appears in the reconciliation
        findings, so "we meant to skip it" cannot be used to quiet a mismatch
        nobody has resolved. See `unaccounted`.
        """
        if not reason:
            raise ValueError(f"{code}: an exclusion must carry a reason")
        self._record(EntityOutcome(code, EXCLUDED, reason=reason))

    # ── One terminal outcome per entity ─────────────────────────────────────

    def _record(self, outcome: EntityOutcome) -> None:
        """Append, refusing a second verdict for the same entity.

        Exactly one terminal outcome per attempted entity. Two verdicts mean
        the loop double-counted or retried without resetting, and whichever
        the reader believes is a coin toss -- `usable` and `empty` for the
        same code cannot both be true of one run.
        """
        prior = next((o for o in self.outcomes if o.code == outcome.code), None)
        if prior is not None:
            raise ValueError(
                f"{outcome.code}: already recorded as {prior.outcome!r}, "
                f"cannot also be {outcome.outcome!r} — one terminal outcome "
                f"per entity")
        self.outcomes.append(outcome)

    @property
    def recorded(self) -> frozenset[str]:
        return frozenset(o.code for o in self.outcomes)

    @property
    def unaccounted(self) -> frozenset[str]:
        """Eligible entities with no outcome at all.

        Not "failed" and not "excluded" — simply never reached a verdict. A
        loop that breaks early, a continue that skips the recording, an
        entity filtered out upstream: each leaves a silent hole, and a hole
        is what every defect in this file began as.
        """
        if self.population is None:
            return frozenset()
        return frozenset(self.population.eligible - self.recorded)

    # ── Run state ───────────────────────────────────────────────────────────

    @property
    def failures(self) -> list[EntityOutcome]:
        return [o for o in self.outcomes if o.outcome in FAILING_OUTCOMES]

    @property
    def degraded(self) -> bool:
        """Some eligible entity did not publish, but others did.

        Degraded is a state, not a failure: the entities that succeeded are
        published, and the run still reports that something is wrong. A
        persistent per-entity failure has to stay visible rather than
        averaging into a green run.
        """
        if self.usable == 0:
            return False            # that is failure, not degradation
        if self.failures or self.unaccounted:
            return True
        return bool(self.population and not self.population.reconciled)

    @property
    def summary(self) -> str:
        line = (f"{self.producer}: {self.usable}/{self.expected} obtained, "
                f"{self.refused} refused, {self.empty} empty, "
                f"{self.rows} rows")
        if self.population and not self.population.reconciled:
            line += (f"; {len(self.population.omitted)} omitted, "
                     f"{len(self.population.stale_configured)} stale")
        return line

    def report(self) -> list[str]:
        """Human-readable findings. Empty when the run was clean."""
        out = list(self.population.findings()) if self.population else []
        out += [str(o) for o in self.failures]
        if self.unaccounted:
            out.append("eligible but never reached a verdict: "
                       + ", ".join(sorted(self.unaccounted)))
        return out

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
