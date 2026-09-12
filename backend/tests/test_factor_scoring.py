"""
The declared model, executed
============================
factor_model.py declares which signals compose a factor and in what
proportion. These tests prove the scoring engine obeys that declaration
against a real frame, rather than the declaration being aspirational while
``skipna=True`` quietly decides the weights.

The two branches that must never converge:

    D/E NOT_MEANINGFUL for a bank    reweight, explicitly, to the survivors
    ROE UNAVAILABLE                  refuse — do not rescale to four signals

Both are "one constituent absent". Same arity of loss, opposite answers.

Requires psycopg2 (composite_score imports it at module scope). Run under the
server venv:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_factor_scoring.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Assessment,
    Cause,
    Domain,
)
from compute.engine.composite_score import compute_factor  # noqa: E402
from compute.engine.factor_model import model_for  # noqa: E402
from compute.engine.universe_writer import column_for  # noqa: E402

V2 = "FACTOR_MODEL_V2"
QUALITY = model_for(V2)["quality"]
CONSTITUENTS = [c.metric for c in QUALITY.constituents]

#: Five companies, ascending on every constituent, so percentile ranks are
#: exactly 20/40/60/80/100 and a score can be predicted rather than observed.
CODES = ["A", "B", "C", "D", "E"]


def frame() -> pd.DataFrame:
    data = {"asx_code": CODES}
    for metric in CONSTITUENTS:
        column = column_for(metric)
        # debt_to_equity is direction -1, so give it a descending series to
        # keep every company's rank identical across constituents. That makes
        # an equal-weight score exactly equal to its own percentile.
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        if metric == "debt_to_equity":
            values = list(reversed(values))
        data[column] = values
    return pd.DataFrame(data)


def applicable(metric: str) -> Assessment:
    return Assessment(metric, Applicability.APPLICABLE, 1.0, "",
                      Domain.GENERAL_CORPORATE)


def assessments(**overrides) -> dict:
    """Every company fully applicable, with named exceptions for company E."""
    out = {code: {m: applicable(m) for m in CONSTITUENTS} for code in CODES}
    for metric, assessment in overrides.items():
        out["E"][metric] = assessment
    return out


def score(assess: dict = None) -> pd.Series:
    df = frame()
    return compute_factor(df, "quality", QUALITY, assess, model_version=V2)


# ── Deterministic under the declared model ───────────────────────────────────

def test_all_applicable_scores_each_company_at_its_own_percentile():
    """Every constituent ranks the companies identically, so an equal-weight
    model must reproduce that ranking exactly. Any deviation means the weights
    are not the declared ones."""
    s = score(assessments())

    assert list(s) == [20.0, 40.0, 60.0, 80.0, 100.0]


def test_the_score_is_reproducible():
    assert list(score(assessments())) == list(score(assessments()))


# ── Out of domain reweights, explicitly ──────────────────────────────────────

def test_a_bank_reweights_around_its_out_of_domain_signals():
    """D/E and net margin are NOT_MEANINGFUL for a bank. Quality runs on the
    remaining three, which rank company E first, so its score is unchanged —
    what changes is that three signals produced it rather than five, under a
    declared policy rather than a NaN."""
    nm = lambda m: Assessment(m, Applicability.NOT_MEANINGFUL, None,  # noqa: E731
                              "out of domain", Domain.BANK, cause=Cause.DOMAIN)
    s = score(assessments(debt_to_equity=nm("debt_to_equity"),
                          net_margin=nm("net_margin")))

    assert not pd.isna(s.iloc[4]), "a bank still receives a quality score"
    assert s.iloc[4] == 100.0, \
        "E leads on the three surviving signals, so it still leads"


def test_every_constituent_out_of_domain_is_no_score():
    nm = lambda m: Assessment(m, Applicability.NOT_MEANINGFUL, None,  # noqa: E731
                              "out of domain", Domain.BANK, cause=Cause.DOMAIN)
    s = score(assessments(**{m: nm(m) for m in CONSTITUENTS}))

    assert pd.isna(s.iloc[4]), \
        "a company none of whose quality signals apply has no quality score, " \
        "not a low one"


# ── Unavailable refuses, and does not rescale ────────────────────────────────

def test_an_unavailable_constituent_makes_the_factor_unavailable():
    """The acceptance case. Replacing one required applicable observation with
    source-unavailable must withhold the factor, not rescale it to four."""
    gone = Assessment("roe", Applicability.UNAVAILABLE, None, "no value",
                      Domain.GENERAL_CORPORATE, cause=Cause.SOURCE_MISSING)
    s = score(assessments(roe=gone))

    assert pd.isna(s.iloc[4]), "quality must be withheld, not renormalised"
    assert list(s.iloc[:4]) == [20.0, 40.0, 60.0, 80.0], \
        "the other companies are unaffected"


def test_a_source_unhealthy_constituent_is_not_helpfully_renormalised():
    """The case most likely to regress later, because rescaling around a
    broken feed looks like resilience."""
    broken = Assessment("roce", Applicability.UNAVAILABLE, None,
                        "feed incomplete", Domain.GENERAL_CORPORATE,
                        cause=Cause.SOURCE_UNHEALTHY)
    assert pd.isna(score(assessments(roce=broken)).iloc[4])


def test_insufficient_history_also_refuses():
    thin = Assessment("net_margin", Applicability.INSUFFICIENT_DATA, None,
                      "one year", Domain.GENERAL_CORPORATE,
                      cause=Cause.INSUFFICIENT_HISTORY)
    assert pd.isna(score(assessments(net_margin=thin)).iloc[4])


# ── Piotroski is not a V2 constituent ────────────────────────────────────────

def test_supplying_piotroski_cannot_change_v2_quality():
    """Not declared, so no value, NaN or unsupported state for it may move the
    score. Zero weight because it is absent from the model, not because its
    value went missing."""
    baseline = list(score(assessments()))

    for supplied in (
        applicable("piotroski_f_score"),
        Assessment("piotroski_f_score", Applicability.UNAVAILABLE, None,
                   "unsupported", Domain.GENERAL_CORPORATE,
                   cause=Cause.COMPUTATION_UNSUPPORTED),
    ):
        assert list(score(assessments(piotroski_f_score=supplied))) == baseline


def test_a_declared_column_missing_from_the_frame_raises():
    """A contract error, not a company with no data."""
    df = frame().drop(columns=[column_for("roe")])
    try:
        compute_factor(df, "quality", QUALITY, assessments(), model_version=V2)
    except KeyError as exc:
        assert "roe" in str(exc)
    else:
        raise AssertionError("a missing declared column must not score as NaN")


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
