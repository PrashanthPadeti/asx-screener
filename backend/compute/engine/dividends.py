"""
TTM dividend window and per-payment gross-up
=============================================
The canonical trailing-twelve-month dividend calculation. Replaces two defects
that lived in ``daily_compute.compute_metrics``:

    ttm_dps      = sum(d["amount"] for d in divs[:4])
    avg_franking = mean(franking_pct for d in divs[:4])
    grossed_up   = ttm_dps * (1 + avg_franking/100 * 0.30/0.70)

``divs[:4]`` is TTM only for a quarterly payer. The ASX pays semi-annually, so
for most of the market that summed **two years** — CBA's grossed-up yield read
8.73% against a true 4.95c/$1.5869 basis. And franking was averaged across
payments then applied to the aggregate, so a company that changed franking
between payments was grossed up on a number that matched no payment it made.

Two rules replace them:

    TTM is period-based, not payment-count based.
    Gross up per payment, then sum. Never per aggregate.

``market.dividends.grossed_up_amount`` already holds the per-payment figure —
``fetch_dividends`` selected it, returned it as ``d["grossed_up"]``, and nothing
read it. Where it is present and plausible it wins, because it preserves
whatever payment-level tax treatment produced the record; a 30% company rate is
not safe to assume for every payment. Where it is absent we reconstruct per
payment, and say so in ``provenance`` — mixing stored and reconstructed
per-payment values is fine, but it must never be silent.

Frankiing percentage is *derived back* from the summed cash and gross rather
than averaged, which makes the relationship the screener asserts true by
construction rather than by luck:

    grossed_up_yield / dividend_yield  ==  1 + franking_pct/100 * (t/(1-t))

Usage:
    res = ttm_dividends(payments, as_of=snapshot_date)
    res.cash_dps, res.gross_dps, res.franking_pct, res.state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Iterable, Optional, Sequence

# Australian company tax rate used when reconstructing a missing gross-up.
# Only ever applied per payment, and only when no stored value is usable.
CORP_TAX_RATE = 0.30

# cash * (1 + 1.00 * 0.30/0.70) = cash * 1.428571 is the maximum a fully franked
# payment can reach at the 30% rate. Base-rate entities (25%) gross up *less*,
# so the ceiling is the binding check. A little headroom above it absorbs
# rounding and historical rate differences; anything beyond is not a gross-up.
MAX_GROSS_RATIO = 1.50

# Absolute tolerance, in dollars per share, for calling a stored gross-up
# consistent with the 30% formula. Dividends are stored to the cent or finer.
RECONCILE_TOL = 0.0005


class GrossUpPolicy(str, Enum):
    """How a payment's grossed-up amount is chosen.

    PREFER_STORED is the default and the one the roadmap specifies: the stored
    per-payment value wins wherever it is present and plausible, and only a
    missing value is reconstructed. The other two exist so the preflight can be
    answered empirically rather than argued — run the same universe under each
    and compare, rather than guessing which the data supports.
    """

    PREFER_STORED = "prefer_stored"   # stored where plausible, else reconstruct
    STRICT_STORED = "strict_stored"   # stored only; missing => unavailable
    COMPUTE_ONLY = "compute_only"     # ignore stored; reconstruct every payment


class DividendState(str, Enum):
    """Why a TTM figure is or is not available.

    Mirrors the applicability contract's four states. ``NOT_MEANINGFUL`` is
    deliberately absent: a company that pays no dividend has a *meaningful*
    yield of zero-or-none, not an inapplicable one. Domain suppression is the
    applicability layer's job, not this module's.
    """

    APPLICABLE = "applicable"
    NO_PAYMENTS_IN_WINDOW = "no_payments_in_window"   # paid before, not lately
    NO_DIVIDEND_HISTORY = "no_dividend_history"       # never paid, or no rows
    UNAVAILABLE = "unavailable"                       # rows exist, unusable


@dataclass(frozen=True)
class Payment:
    """One dividend payment, normalised out of ``market.dividends``."""

    ex_date: date
    cash: float
    franking_pct: Optional[float] = None
    stored_gross: Optional[float] = None


@dataclass(frozen=True)
class GrossedPayment:
    """A payment with its gross-up resolved, and the reason for that choice."""

    payment: Payment
    gross: float
    provenance: str          # "stored" | "reconstructed" | "unfranked"
    reconciles: Optional[bool] = None   # vs the 30% formula; None if untestable


@dataclass(frozen=True)
class TTMDividends:
    """The result of one trailing-twelve-month calculation."""

    cash_dps: Optional[float]
    gross_dps: Optional[float]
    franking_pct: Optional[float]
    state: DividendState
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    payment_count: int = 0
    provenance: str = "none"          # "stored" | "reconstructed" | "mixed"
    payments: tuple[GrossedPayment, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.state is DividendState.APPLICABLE


# ── Normalisation ─────────────────────────────────────────────────────────────

def _as_date(v) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    raise TypeError(f"unsupported date value: {v!r}")


def _as_float(v) -> Optional[float]:
    """Decimal, str, int or float to float. NUMERIC columns arrive as Decimal."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalise(rows: Iterable[dict]) -> list[Payment]:
    """Turn ``fetch_dividends`` rows into Payments, dropping unusable ones.

    A row with no ex-date cannot be placed in a window and a row with no cash
    amount cannot be summed, so neither can contribute. They are dropped here
    rather than guarded at every later step.
    """
    out: list[Payment] = []
    for r in rows:
        ex = _as_date(r.get("ex_date"))
        cash = _as_float(r.get("amount") if "amount" in r else r.get("amount_per_share"))
        if ex is None or cash is None:
            continue
        out.append(Payment(
            ex_date=ex,
            cash=cash,
            franking_pct=_as_float(r.get("franking_pct")),
            stored_gross=_as_float(r.get("grossed_up") if "grossed_up" in r
                                   else r.get("grossed_up_amount")),
        ))
    return out


# ── The window ────────────────────────────────────────────────────────────────

def ttm_window(as_of: date) -> tuple[date, date]:
    """The trailing twelve months ending at ``as_of``, inclusive of both ends.

    Twelve months back is expressed as (same day, previous year) + 1 day rather
    than 365 days, so leap years do not silently widen or narrow the window.
    """
    try:
        start = as_of.replace(year=as_of.year - 1)
    except ValueError:          # 29 Feb in a non-leap prior year
        start = as_of.replace(year=as_of.year - 1, month=2, day=28)
    return start + timedelta(days=1), as_of


def in_window(payments: Sequence[Payment], as_of: date) -> list[Payment]:
    """Payments whose ex-date falls in the trailing twelve months.

    Period-based, so semi-annual, quarterly, monthly, irregular and
    frequency-changing payers all work without encoding an assumed cadence.
    Specials are included: they are eligible dividends actually received.
    """
    start, end = ttm_window(as_of)
    return sorted(
        (p for p in payments if start <= p.ex_date <= end),
        key=lambda p: p.ex_date,
        reverse=True,
    )


# ── Per-payment gross-up ──────────────────────────────────────────────────────

def franking_credit(cash: float, franking_pct: Optional[float],
                    tax_rate: float = CORP_TAX_RATE) -> float:
    """The imputation credit attached to one payment.

    credit = cash * franked_proportion * t/(1-t)

    At the 30% rate a fully franked dollar carries 42.86c of credit, so the
    grossed-up payment is 1.4286x the cash — the ratio the screener's
    reconciliation test asserts.
    """
    pct = max(0.0, min(100.0, franking_pct or 0.0))
    return cash * (pct / 100.0) * (tax_rate / (1.0 - tax_rate))


def _plausible(cash: float, gross: Optional[float]) -> bool:
    """Is a stored gross-up arithmetically possible for this cash amount?

    A gross-up is never below the cash it grosses up, and never above the fully
    franked ceiling. Values outside that are not conservative-but-wrong, they
    are a different quantity — a total distribution, a prior year, a unit error
    — and must not be summed into a yield.
    """
    if gross is None or cash <= 0:
        return False
    return cash <= gross <= cash * MAX_GROSS_RATIO


def gross_up(payment: Payment, policy: GrossUpPolicy = GrossUpPolicy.PREFER_STORED,
             tax_rate: float = CORP_TAX_RATE) -> Optional[GrossedPayment]:
    """Resolve one payment's grossed-up amount.

    Returns None only under STRICT_STORED with no usable stored value — the
    caller then treats the whole series as unavailable rather than quietly
    summing a partial one.
    """
    cash, stored = payment.cash, payment.stored_gross

    computed = cash + franking_credit(cash, payment.franking_pct, tax_rate)
    reconciles = (abs(stored - computed) < RECONCILE_TOL) if stored is not None else None

    if policy is not GrossUpPolicy.COMPUTE_ONLY and _plausible(cash, stored):
        return GrossedPayment(payment, stored, "stored", reconciles)

    if policy is GrossUpPolicy.STRICT_STORED:
        return None

    provenance = "unfranked" if not payment.franking_pct else "reconstructed"
    return GrossedPayment(payment, computed, provenance, reconciles)


# ── The calculation ───────────────────────────────────────────────────────────

def implied_franking_pct(cash_dps: float, gross_dps: float,
                         tax_rate: float = CORP_TAX_RATE) -> Optional[float]:
    """The franking percentage the summed cash and gross actually imply.

    Derived rather than averaged, which is what keeps the displayed trio
    self-consistent: a row can no longer show a grossed-up yield that its own
    cash yield and franking percentage cannot produce. Unfranked gives exactly
    0.0 and fully franked exactly 100.0.
    """
    if cash_dps <= 0:
        return None
    ratio = gross_dps / cash_dps - 1.0
    pct = ratio / (tax_rate / (1.0 - tax_rate)) * 100.0
    return max(0.0, min(100.0, pct))


def ttm_dividends(rows: Iterable[dict] | Sequence[Payment],
                  as_of: Optional[date] = None,
                  policy: GrossUpPolicy = GrossUpPolicy.PREFER_STORED,
                  tax_rate: float = CORP_TAX_RATE) -> TTMDividends:
    """Trailing-twelve-month cash and grossed-up dividends per share.

    ``as_of`` is the metric snapshot date, not today: a metric computed for a
    past date must select the window that date saw. It defaults to today only
    for interactive use.
    """
    as_of = as_of or date.today()

    payments = list(rows) if rows and isinstance(next(iter(rows), None), Payment) \
        else normalise(rows)  # type: ignore[arg-type]

    if not payments:
        return TTMDividends(None, None, None, DividendState.NO_DIVIDEND_HISTORY)

    window = in_window(payments, as_of)
    start, end = ttm_window(as_of)

    if not window:
        return TTMDividends(None, None, None, DividendState.NO_PAYMENTS_IN_WINDOW,
                            window_start=start, window_end=end)

    grossed = [gross_up(p, policy, tax_rate) for p in window]
    if any(g is None for g in grossed):
        return TTMDividends(None, None, None, DividendState.UNAVAILABLE,
                            window_start=start, window_end=end,
                            payment_count=len(window))

    resolved: list[GrossedPayment] = [g for g in grossed if g is not None]
    cash_dps = sum(g.payment.cash for g in resolved)
    gross_dps = sum(g.gross for g in resolved)

    if cash_dps <= 0:
        # Payments summing to zero or less carry no yield. SFR showed 100%
        # franking against no dividend; that must not become a franking figure
        # hanging off a null cash basis.
        return TTMDividends(None, None, None, DividendState.UNAVAILABLE,
                            window_start=start, window_end=end,
                            payment_count=len(window))

    sources = {g.provenance for g in resolved}
    provenance = ("stored" if sources <= {"stored"}
                  else "reconstructed" if sources <= {"reconstructed", "unfranked"}
                  else "mixed")

    return TTMDividends(
        cash_dps=cash_dps,
        gross_dps=gross_dps,
        franking_pct=implied_franking_pct(cash_dps, gross_dps, tax_rate),
        state=DividendState.APPLICABLE,
        window_start=start,
        window_end=end,
        payment_count=len(resolved),
        provenance=provenance,
        payments=tuple(resolved),
    )


# ── Screener-facing metrics ───────────────────────────────────────────────────

def dividend_metrics(rows: Iterable[dict] | Sequence[Payment],
                     close: Optional[float],
                     as_of: Optional[date] = None,
                     policy: GrossUpPolicy = GrossUpPolicy.PREFER_STORED,
                     tax_rate: float = CORP_TAX_RATE) -> dict:
    """The five dividend fields, always all five, never partially written.

    Every key is present on every path. ``upsert_metrics`` builds its UPDATE
    clause from the keys in this dict, so an omitted field silently keeps
    whatever the previous run wrote — which is how OEL carried a 480%
    grossed-up yield long after it stopped paying anything.
    """
    res = ttm_dividends(rows, as_of=as_of, policy=policy, tax_rate=tax_rate)

    empty = {
        "dividend_per_share": None,
        "dividend_yield": None,
        "franking_pct": None,
        "grossed_up_dividend": None,
        "grossed_up_yield": None,
    }

    if not res.ok or not close or close <= 0:
        return empty

    return {
        "dividend_per_share": round(res.cash_dps, 4),
        "dividend_yield": round(res.cash_dps / close, 6),
        "franking_pct": round(res.franking_pct, 2) if res.franking_pct is not None else None,
        "grossed_up_dividend": round(res.gross_dps, 4),
        "grossed_up_yield": round(res.gross_dps / close, 6),
    }


def reconciles(metrics: dict, tax_rate: float = CORP_TAX_RATE,
               tol: float = 1e-4) -> bool:
    """The invariant every screener row must satisfy.

        grossed_up_yield / dividend_yield == 1 + franking_pct/100 * t/(1-t)

    with equality of the two yields when nothing is franked. This is the test
    that ``build_screener_universe`` currently fails by assembling the three
    fields from three different provenances.
    """
    dy = metrics.get("dividend_yield")
    gy = metrics.get("grossed_up_yield")
    fp = metrics.get("franking_pct")

    if dy is None and gy is None:
        return True
    if dy is None or gy is None or dy <= 0:
        return False
    if gy < dy - tol:
        return False

    expected = 1.0 + (fp or 0.0) / 100.0 * (tax_rate / (1.0 - tax_rate))
    return abs(gy / dy - expected) < tol
