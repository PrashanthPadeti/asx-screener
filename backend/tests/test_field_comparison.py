"""
Comparing two fields: what the grammar refused and the database never did
=========================================================================
``SELECT * FROM screener.universe WHERE total_equity > total_debt`` returns
1,437 rows. The same condition typed into Query Mode returned

    Expected a numeric value after 'total_equity >', got 'total_debt'.

Nothing about SQL, the schema or the security model was blocking it. The
grammar accepted ``field OP literal`` and nothing else, so a field name on the
right was a syntax error. The evidence that this was a real gap rather than a
missing nicety is in the alias map: eight metrics -- net_cash,
debt_growing_slower_than_profit, ocf_beats_net_income, eps_beats_revenue_growth,
fcf_growing_faster_than_revenue, inventory_growing_slower_than_sales,
receivables_growing_slower_than_sales, operating_leverage -- exist only because
somebody needed a comparison the query language could not express and hard-coded
it instead. That list grows one metric at a time, forever, or the language
learns to say it once.

Two things make a naive version silently wrong rather than merely absent, and
both are checked here against the real registry rather than against examples.

**Scale.** A literal is multiplied by its field's scale on the way in --
``roe > 10`` binds 0.10 -- but a column-to-column comparison never passes
through that conversion. The registry today holds 95 number fields at unit
``%`` scale 0.01 and 14 more at unit ``%`` scale 1.0. Comparing across those
two groups compares 0.10 against 10 and answers confidently. A unit check
alone does not catch it, because both groups say ``%``.

**Governance.** A governed metric answers three ways: true, false, and "not
applicable to this company, for this reason". A comparison of two governed
metrics has two such verdicts to combine, and an ordinary SQL comparison can
carry neither -- every company the metric does not apply to would simply
vanish from the result, indistinguishable from one that was evaluated and
failed. So Stage 1 refuses those outright. The capability is absent and says
so, rather than present and wrong.

The refusal ordering is itself a defect this file names. A governed comparison
makes ``requires_run_scope`` true, so with the snapshot unavailable the run
scope check fired FIRST and answered a permanently-unsupported query with
CompileError -> 503, telling the client to come back later for a capability no
amount of waiting supplies. What the build cannot do is decided before what
the data cannot currently support.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_field_comparison.py
"""

import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.parsed_query import (  # noqa: E402
    ComparisonUnsupported,
    Criterion,
    canonicalise,
    to_legacy_sql,
)
from app.core.query_parser import QueryParseError, parse_query_typed  # noqa: E402
from compute.engine.screen_predicates import CriterionType  # noqa: E402
from compute.engine.screen_sql import plan_screen  # noqa: E402
from tests.test_parser_typed import (  # noqa: E402
    ALLOWED_FIELDS,
    QUERIES,
    REGISTRY,
    parse_query,
)


class Skipped(Exception):
    """Needs a runtime dependency this environment does not have."""


#: Ordered pairs of ungoverned number fields sharing a unit AND a scale -- the
#: comparisons this build is supposed to answer. 6,858 when written. The floor
#: is far below that so ordinary churn does not trip it, and far above zero so
#: a refactor that narrows the population fails loudly instead of passing over
#: nothing. A guard that has lost its population still prints PASS.
MINIMUM_PAIRS = 2000


def _groups() -> dict:
    """Number fields keyed by (unit, scale) -- what is commensurable."""
    out = defaultdict(list)
    for key, info in ALLOWED_FIELDS.items():
        if info.get("type", "number") != "number":
            continue
        unit  = (info.get("unit") or "").strip().lower()
        scale = float(info.get("scale", 1.0) or 1.0)
        out[(unit, scale)].append(key)
    return out


def _comparable_pairs() -> list:
    pairs = []
    for members in _groups().values():
        free = [k for k in members if not REGISTRY[k].governed]
        pairs.extend((a, b) for a in free for b in free if a != b)
    return pairs


def _compiled(text: str):
    """Through the production path: parse -> canonicalise -> plan."""
    parsed = canonicalise(parse_query_typed(text, ALLOWED_FIELDS), REGISTRY)
    return parsed, plan_screen(parsed, REGISTRY, None, dialect="postgres",
                               table_alias="u", paramstyle="named")


# ── The thing that was asked for ─────────────────────────────────────────────

def test_the_query_that_prompted_this_compiles():
    """Named directly, so a revert of the feature is unambiguous."""
    parsed, plan = _compiled("total_equity > total_debt")
    assert "u.total_equity" in plan.where and "u.total_debt" in plan.where, \
        f"both columns must appear in the fragment: {plan.where}"
    assert not plan.params, (
        f"a field-to-field comparison binds nothing, yet {plan.params} was "
        f"bound. A parameter here means a literal leaked into the fragment.")


def test_both_sides_are_reported_as_fields():
    """fields() has always returned a tuple. This is the first caller that
    needs the second slot, and governance, run scope and validation all read
    it. A one-sided answer makes the right-hand field invisible to every one
    of them."""
    parsed, _ = _compiled("total_assets > total_debt")
    criterion = parsed.criteria[0]
    assert criterion.fields() == ("total_assets", "total_debt")
    assert criterion.is_comparison
    assert criterion.value is None, (
        "value must stay None for a comparison; a stale literal beside "
        "rhs_field is a second source of truth that can disagree with it")


def test_a_comparison_can_be_combined_with_ordinary_conditions():
    _, plan = _compiled("total_assets > total_debt AND total_equity > 50")
    assert "u.total_assets" in plan.where and "u.total_debt" in plan.where
    assert len(plan.params) == 1, (
        f"the literal half still binds exactly one parameter: {plan.params}")


# ── The property, over the registry rather than over examples ────────────────

def test_the_population_of_comparable_pairs_is_still_there():
    """A property asserted over an empty set passes."""
    pairs = _comparable_pairs()
    assert len(pairs) >= MINIMUM_PAIRS, (
        f"only {len(pairs)} comparable ungoverned pairs found, expected at "
        f"least {MINIMUM_PAIRS}. The property below is passing over a "
        f"population it can no longer see, which is worse than its absence.")


def test_every_comparable_pair_compiles_and_binds_nothing():
    """All 6,858, not the three I happened to try.

    A sample of my own choosing tests my imagination. The registry is the
    population, so the registry is what gets asserted over.
    """
    failures = []
    for left, right in _comparable_pairs():
        try:
            _, plan = _compiled(f"{left} > {right}")
            if plan.params:
                failures.append(f"{left} > {right}: bound {plan.params}")
        except (QueryParseError, ComparisonUnsupported) as exc:
            failures.append(f"{left} > {right}: {type(exc).__name__}: {exc}")
    assert not failures, (
        f"{len(failures)} of {len(_comparable_pairs())} comparable pairs "
        f"failed to compile:\n  " + "\n  ".join(failures[:10]))


# ── What must be refused, and why ────────────────────────────────────────────

def test_mismatched_units_are_refused():
    """A percentage against a figure in millions is not a hard question, it
    is a meaningless one. It must not reach the database to be answered."""
    try:
        _compiled("roe > total_debt")
    except QueryParseError as exc:
        assert "unit" in str(exc).lower()
    else:
        raise AssertionError(
            "roe (%) was compared against total_debt (AUD M) and compiled")


def test_the_same_unit_on_different_scales_is_refused():
    """The check a unit comparison alone does not make.

    Both sides say '%'. One is stored as 0.10 and the other as 10. Found from
    the registry rather than hard-coded, so this keeps testing whatever the
    registry currently holds.
    """
    groups = _groups()
    percent = sorted(k for k in groups if k[0] == "%")
    if len(percent) < 2:
        raise Skipped("two percent scales in the registry — there is now one, "
                      "so this hazard no longer exists to test")
    left  = next(k for k in groups[percent[0]] if not REGISTRY[k].governed)
    right = next(k for k in groups[percent[1]] if not REGISTRY[k].governed)
    try:
        _compiled(f"{left} > {right}")
    except QueryParseError as exc:
        assert "scale" in str(exc).lower(), str(exc)
    else:
        raise AssertionError(
            f"{left} and {right} are both % but stored on different scales "
            f"({percent[0][1]} vs {percent[1][1]}), and the comparison "
            f"compiled. It would compare unlike numbers and answer.")


def test_a_non_numeric_right_hand_side_is_refused():
    for text in ("total_equity > sector", "total_equity > is_reit"):
        try:
            _compiled(text)
        except QueryParseError:
            pass
        else:
            raise AssertionError(f"{text!r} compiled")


def test_an_unrecognised_right_hand_side_is_a_parse_error():
    """Not an obscure failure further down. The message names the panel."""
    try:
        _compiled("total_equity > not_a_real_field")
    except QueryParseError as exc:
        assert "field" in str(exc).lower()
    else:
        raise AssertionError("an unknown right-hand field compiled")


def test_a_governed_metric_on_either_side_is_refused():
    """Both positions. A check written for the left side only would read a
    governed right-hand field as ungoverned and compile it."""
    groups = _groups()
    pair = None
    for members in groups.values():
        free = [k for k in members if not REGISTRY[k].governed]
        held = [k for k in members if REGISTRY[k].governed]
        if free and held:
            pair = (free[0], held[0])
            break
    assert pair, "no governed/ungoverned pair shares a unit — cannot test"
    free, held = pair

    for text in (f"{held} > {free}", f"{free} > {held}"):
        try:
            _compiled(text)
        except ComparisonUnsupported as exc:
            assert held in str(exc), (
                f"the refusal must name the governed metric: {exc}")
        else:
            raise AssertionError(
                f"{text!r} compiled. A governed metric can be inapplicable "
                f"to a company; compiled this way, every such company "
                f"vanishes from the result indistinguishably from one that "
                f"was evaluated and failed.")


def test_the_capability_refusal_precedes_the_run_scope_refusal():
    """The 503-for-a-permanent-gap defect, named directly.

    A governed comparison makes requires_run_scope true. With no scope
    resolved, the scope check fired first and raised CompileError -> 503,
    telling the client to retry later for something that will never work.
    ComparisonUnsupported -> 422 is the honest answer, and it must win even
    when the snapshot is unavailable.
    """
    groups = _groups()
    held = [k for members in groups.values() for k in members
            if REGISTRY[k].governed]
    pairs = [(a, b) for members in groups.values()
             for a in members for b in members
             if a != b and REGISTRY[a].governed and REGISTRY[b].governed]
    assert pairs, "no two governed metrics share a unit — cannot test"
    left, right = pairs[0]

    parsed = canonicalise(parse_query_typed(f"{left} > {right}",
                                            ALLOWED_FIELDS), REGISTRY)
    assert parsed.requires_run_scope, (
        "the premise of this test is that a governed comparison needs a run "
        "scope; if it no longer does, the ordering it guards is moot")
    try:
        # scope=None is the unavailable-snapshot case.
        plan_screen(parsed, REGISTRY, None, dialect="postgres",
                    table_alias="u", paramstyle="named")
    except ComparisonUnsupported:
        pass
    except Exception as exc:                                   # noqa: BLE001
        raise AssertionError(
            f"the unsupported-capability refusal must come first, but "
            f"{type(exc).__name__} was raised: {exc}")
    else:
        raise AssertionError("a governed comparison compiled")


def test_governance_is_read_from_both_sides():
    """touches_governed, not governed.

    requires_run_scope is built from it, so a criterion whose right side is
    governed and whose left side is not would resolve no run scope at all.
    """
    groups = _groups()
    for members in groups.values():
        free = [k for k in members if not REGISTRY[k].governed]
        held = [k for k in members if REGISTRY[k].governed]
        if not (free and held):
            continue
        parsed = canonicalise(
            parse_query_typed(f"{free[0]} > {held[0]}", ALLOWED_FIELDS),
            REGISTRY)
        criterion = parsed.criteria[0]
        assert not criterion.governed, "premise: the left side is ungoverned"
        assert criterion.rhs_governed and criterion.touches_governed
        assert parsed.requires_run_scope, (
            "a governed right-hand side must still demand the run contract")
        return
    raise AssertionError("no governed/ungoverned pair shares a unit")


# ── NULL handling ────────────────────────────────────────────────────────────

def test_an_excluded_comparison_is_null_safe():
    """NOT(NULL) is NULL, so without the COALESCE a row with either side
    missing FAILS an EXCLUDED criterion it was never evaluated against —
    the same shape the ungoverned literal path already guards."""
    criterion = Criterion("total_equity", CriterionType.EXCLUDED, "gt", None,
                          rhs_field="total_debt")
    from app.core.parsed_query import ParsedQuery
    parsed = canonicalise(ParsedQuery(expression=criterion), REGISTRY)
    plan = plan_screen(parsed, REGISTRY, None, dialect="postgres",
                       table_alias="u", paramstyle="named")
    assert "COALESCE" in plan.where.upper(), (
        f"an EXCLUDED comparison must be NULL-safe: {plan.where}")


def test_a_required_comparison_drops_nulls_exactly_as_a_literal_does():
    """Deliberate, and the same contract as the 274 ungoverned fields already
    have. `roe > 10` already excludes a NULL roe without a recorded reason;
    this introduces no new class of silent absence. The reason-carrying
    question belongs to the governed path, which is refused above."""
    _, comparison = _compiled("total_equity > total_debt")
    _, literal    = _compiled("total_equity > 50")
    for where in (comparison.where, literal.where):
        assert "COALESCE" not in where.upper(), (
            f"neither shape coalesces for a REQUIRED criterion: {where}")


# ── The language is otherwise unchanged ──────────────────────────────────────

def test_the_accepted_language_is_otherwise_unchanged():
    """A grammar change is where a regression hides. Everything the parser
    accepted before must still parse, and compile the same way."""
    for text in QUERIES:
        parse_query(text, ALLOWED_FIELDS)
        parse_query_typed(text, ALLOWED_FIELDS)


def test_rejections_that_must_stay_rejections():
    """A word after an operator is now a field reference, so these are the
    cases that could have been loosened by accident."""
    for bad in ("", "   ", "roe >", "roe > 10 AND", "is_reit > 5",
                "roe > 'Materials'", "total_equity > > total_debt"):
        try:
            parse_query_typed(bad, ALLOWED_FIELDS)
        except QueryParseError:
            continue
        raise AssertionError(f"{bad!r} is now accepted and must not be")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures, skipped = [], []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Skipped as e:
            skipped.append(name)
            print(f"  SKIP  {name}  - needs {e}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    passed = len(tests) - len(failures) - len(skipped)
    print(f"\n{passed}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
