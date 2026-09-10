"""
Compiling three-valued criteria into SQL without losing the third value
=======================================================================
The predicate semantics are specified in ``screen_predicates``. This is where
they get translated into a WHERE clause, and translation is where they were
going to be lost — a compiler that emits ``debt_to_equity > 1.5`` has silently
decided that a NULL means "not greater than", which is the collapse the whole
contract exists to prevent.

Applicability is expressible in SQL, because the sparse sidecar makes it so:

    applicable(m)  ==  <column> IS NOT NULL AND <states>->'m' IS NULL

Absent from ``metric_states`` means APPLICABLE, so a metric with no entry and
a populated column is the only combination that evaluates. Every other
combination is a non-evaluation with a recorded cause, and the compiler emits
it as such rather than as a comparison that happens to be false.

    REQUIRED    applicable AND predicate
    EXCLUDED    NOT (applicable AND predicate)      -- unproven does not reject
    PREFERRED   applicable AND predicate            -- as a SELECT expression
    ORDERED BY  applicable                          -- as the ranking subset

Two dialects, because the equivalence test needs a real SQL engine and sqlite
is the one available without a server. The Postgres form is what production
runs; the sqlite form exists so the compiled logic can be executed and
compared against the Python engine rather than eyeballed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence

from compute.engine.metric_registry import normalise
from compute.engine.screen_predicates import CriterionType
from compute.engine.universe_writer import column_for

Dialect = Literal["postgres", "sqlite"]

#: Comparison operators a screen definition may use, mapped to SQL. Kept as a
#: closed set: a screen cannot inject an operator, and an unknown one is a
#: definition error rather than something that reaches the database.
OPERATORS: dict[str, str] = {
    "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "eq": "=", "ne": "<>",
}


class CompileError(Exception):
    """A criterion that cannot be compiled honestly."""


@dataclass(frozen=True)
class ValidatedRun:
    """A run the server has established is safe to read through the contract.

    Constructed only from ``screener.compute_runs``, never from anything a
    caller supplied. A route that accepted a run id as a parameter would
    satisfy the positional requirement while still selecting an untrusted
    run — the argument would be present and the guarantee absent.
    """

    run_id: int
    factor_model_version: str
    unhealthy_sources: tuple[str, ...] = ()
    validated: bool = False
    #: Forensic evidence — watermarks, row counts, diagnostic text. Kept on
    #: the run and deliberately absent from contract_key.
    detail: Mapping[str, str] = None

    @property
    def contract_key(self) -> tuple:
        """What must match for two runs to be one logical snapshot.

        Model version and the *semantic* source-health state, and nothing
        else. Two shards that both say ``dividends`` is unhealthy are the same
        logical snapshot even when their watermarks, recent-row counts and
        diagnostic wording differ — that text is evidence about the same fact,
        not a different fact. Letting it into the key would fragment an
        otherwise identical snapshot and refuse a screen for no reason.

        Source health is compared as a *set* of affected sources: which feeds
        were unusable is semantic, how badly and since when is forensic.
        """
        return (self.factor_model_version, tuple(sorted(self.unhealthy_sources)))


#: The query behind resolve_run_scope. Not for a route to execute directly —
#: see the resolver below.
_VALIDATED_RUNS_SQL = """
    SELECT id, factor_model_version, unhealthy_sources, detail
      FROM screener.compute_runs
     WHERE factor_model_version = ANY(%(supported)s)
       AND rows_written IS NOT NULL
     ORDER BY run_at DESC
     LIMIT %(limit)s
"""


def resolve_run_scope(cur, supported_versions: Optional[Sequence[str]] = None,
                      limit: int = 8) -> "RunScope":
    """The server's answer to "which rows may this request read?".

    A service call rather than an SQL snippet a route pastes, because
    "validated" is a capability the server owns: it means a supported model
    version, a completed recompute, and a contract-key check across whatever
    came back. A route importing the query would be one edit away from
    relaxing a condition it did not know was load-bearing.

    Returns the newest coherent scope. Raises when nothing qualifies, because
    no trusted run means no screen — never every row.
    """
    from compute.engine.metric_states import GOVERNED_METRICS

    supported = list(supported_versions or GOVERNED_METRICS.keys())
    cur.execute(_VALIDATED_RUNS_SQL, {"supported": supported, "limit": limit})

    runs = [ValidatedRun(run_id, version, tuple(sources or ()), validated=True,
                         detail=detail)
            for run_id, version, sources, detail in cur.fetchall()]

    if not runs:
        raise CompileError(
            "no completed compute run under a supported factor model; the "
            "recompute has not run, or every run predates this build")

    # Newest first from the query, so the newest contract wins and older
    # incompatible runs are dropped rather than fragmenting the scope.
    newest = runs[0].contract_key
    return RunScope.from_validated_runs(
        [r for r in runs if r.contract_key == newest])


@dataclass(frozen=True)
class RunScope:
    """The runs whose rows may be read through the applicability clause.

    ``metric_states -> 'm' IS NULL`` means APPLICABLE — but only inside a
    validated contract. On a legacy row with a populated numeric column and no
    sidecar, key-absent looks identical to applicable and is in fact
    uninterpretable. The clause is therefore only sound when the query is
    scoped to runs whose model version is supported and whose recompute passed
    the persistence validator.

        Absent sidecar entry means APPLICABLE only inside a validated
        model/run contract. Outside it, absence means uninterpretable.

    Required rather than optional, and enforced once here rather than
    rediscovered per criterion, because the failure mode is silent: every
    predicate would look correct while reading rows that cannot support them.
    """

    run_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.run_ids:
            raise CompileError(
                "a screen must be scoped to at least one validated compute "
                "run; unscoped, an absent sidecar entry on a legacy row is "
                "indistinguishable from an applicable metric")

    def sql(self, dialect: Dialect = "postgres",
            column: str = "compute_run_id") -> str:
        ids = ", ".join(str(int(r)) for r in self.run_ids)
        return f"{column} IN ({ids})"

    @classmethod
    def from_validated_runs(cls, runs: Sequence[ValidatedRun]) -> "RunScope":
        """The only sanctioned way for a route to build a scope.

        Refuses a run the persistence validator has not passed, and refuses a
        mixture of contracts:

            one logical screener snapshot = one validated model/run contract

        Several physical run ids are allowed only where sharding forces it and
        every shard shares a model version and a source-health state. Anything
        else would let a single ranking span two different sets of rules.
        """
        if not runs:
            raise CompileError("no validated compute run is available to read")

        unvalidated = sorted(r.run_id for r in runs if not r.validated)
        if unvalidated:
            raise CompileError(
                f"runs {unvalidated} have not passed persistence validation; "
                f"a scope may only name runs whose recompute was verified")

        contracts = {r.contract_key for r in runs}
        if len(contracts) > 1:
            detail = " vs ".join(str(c) for c in sorted(contracts))
            raise CompileError(
                f"runs span more than one contract ({detail}); a ranking "
                f"across them would compare companies scored under different "
                f"model or source-health states")

        return cls(tuple(sorted(r.run_id for r in runs)))


@dataclass(frozen=True)
class Criterion:
    """One screen condition, in canonical metric identity."""

    metric: str
    criterion: CriterionType
    operator: str
    value: float

    def __post_init__(self) -> None:
        if self.operator not in OPERATORS:
            raise CompileError(
                f"{self.operator!r} is not a permitted operator "
                f"({', '.join(sorted(OPERATORS))})")


def _states_is_null(metric: str, dialect: Dialect, states_col: str) -> str:
    """SQL that is true when the metric has no sidecar entry — i.e. applicable."""
    canonical = normalise(metric)
    if dialect == "postgres":
        return f"{states_col} -> '{canonical}' IS NULL"
    return f"json_extract({states_col}, '$.{canonical}') IS NULL"


def applicable_sql(metric: str, dialect: Dialect = "postgres",
                   states_col: str = "metric_states") -> str:
    """The applicability test, which is the whole reason this module exists.

    Both halves are required. A populated column with a sidecar entry is a
    contract violation rather than a value (see metric_states.violations), and
    a NULL column with no entry is the other one — so a compiler that checked
    only the column, or only the sidecar, would evaluate rows it should not.
    """
    column = column_for(metric)
    return f"({column} IS NOT NULL AND {_states_is_null(metric, dialect, states_col)})"


def predicate_sql(criterion: Criterion, param: str,
                  dialect: Dialect = "postgres") -> str:
    column = column_for(criterion.metric)
    placeholder = f":{param}" if dialect == "sqlite" else f"%({param})s"
    return f"{column} {OPERATORS[criterion.operator]} {placeholder}"


def compile_criterion(criterion: Criterion, param: str,
                      dialect: Dialect = "postgres",
                      states_col: str = "metric_states") -> Optional[str]:
    """One criterion as a WHERE fragment, or None when it constrains nothing.

    PREFERRED and ORDERED BY return None deliberately: neither restricts
    membership. A compiler that folded a preference into the WHERE clause
    would turn a soft signal into a hard filter, which is the same class of
    error as treating a non-evaluation as a failure.
    """
    applicable = applicable_sql(criterion.metric, dialect, states_col)
    predicate = predicate_sql(criterion, param, dialect)

    if criterion.criterion in (CriterionType.REQUIRED, CriterionType.EXCLUDED):
        # Three-valued at the leaf, collapsed to membership by role. Both
        # steps matter: the CASE keeps UNKNOWN from becoming a claim, and the
        # role decides what UNKNOWN means once a decision is unavoidable.
        expression = three_valued_sql(criterion, param, dialect, states_col)
        return f"({membership_sql(expression, criterion.criterion, dialect)})"

    return None


# ── Three-valued composition ──────────────────────────────────────────────────
# The collapse this prevents:
#
#     yield > 5%  on a SOURCE_UNHEALTHY metric  ->  FALSE
#     NOT (yield > 5%)                          ->  TRUE
#
# which turns "we cannot evaluate the dividend yield" into positive evidence
# that the company does not yield more than 5%. Harmless while every governed
# leaf sits directly under a conjunction, and wrong the moment one sits under
# a negation or contributes to a disjunction.
#
# `applicable AND predicate` is a two-valued expression: it says FALSE for
# unavailable, and FALSE is a claim. A CASE that yields NULL says nothing, and
# SQL's own three-valued logic is Kleene logic, so AND, OR and NOT compose it
# correctly without any help:
#
#     NOT UNKNOWN = UNKNOWN        TRUE  AND UNKNOWN = UNKNOWN
#     TRUE  OR UNKNOWN = TRUE      FALSE AND UNKNOWN = FALSE
#     FALSE OR UNKNOWN = UNKNOWN
#
# UNKNOWN becomes a decision only at the membership boundary, and what it
# becomes depends on the role — which is why the role is applied there and not
# at the leaf.

def three_valued_sql(criterion: Criterion, param: str,
                     dialect: Dialect = "postgres",
                     states_col: str = "metric_states") -> str:
    """A governed leaf as TRUE / FALSE / UNKNOWN, with no role applied."""
    applicable = applicable_sql(criterion.metric, dialect, states_col)
    predicate = predicate_sql(criterion, param, dialect)
    return f"CASE WHEN {applicable} THEN ({predicate}) ELSE NULL END"


def membership_sql(expression: str, role: CriterionType,
                   dialect: Dialect = "postgres") -> str:
    """Collapse a three-valued expression into membership, per role.

    REQUIRED  admits only a proven TRUE, so UNKNOWN does not qualify — the
              requirement is unproven.
    EXCLUDED  rejects only a proven TRUE, so UNKNOWN keeps the row — the
              exclusion is unproven.

    Written as an explicit COALESCE rather than `IS TRUE` / `IS NOT TRUE`
    because sqlite has no IS TRUE, and the equivalence suite needs both
    engines to agree on the same text.
    """
    false_literal = "FALSE" if dialect == "postgres" else "0"
    proven_true = f"COALESCE(({expression}), {false_literal})"

    if role is CriterionType.REQUIRED:
        return proven_true
    if role is CriterionType.EXCLUDED:
        return f"NOT {proven_true}"
    raise CompileError(
        f"{role} has no membership meaning; only REQUIRED and EXCLUDED "
        f"decide whether a row is in the result set")


def assert_role_is_decidable(node, under_disjunction: bool = False) -> None:
    """Refuse an EXCLUDED criterion whose meaning is undefined where it sits.

    An exclusion is a top-level statement: "reject rows proven to satisfy
    this". Nested inside a disjunction it has no agreed meaning — is the row
    admitted because the exclusion failed to prove itself, or is the whole
    branch unknown? Rather than pick one and call it the rule, this refuses
    the shape. Guessing at an undefined composition is how the original defect
    arrived.
    """
    from app.core.parsed_query import AllOf, AnyOf
    from app.core.parsed_query import Criterion as TypedCriterion

    if isinstance(node, TypedCriterion):
        if under_disjunction and node.role is CriterionType.EXCLUDED:
            raise CompileError(
                f"EXCLUDED criterion on {node.field!r} sits inside a "
                f"disjunction, where an unproven exclusion has no defined "
                f"meaning. Express it as a top-level exclusion instead.")
        return

    if isinstance(node, AnyOf):
        for operand in node.operands:
            assert_role_is_decidable(operand, under_disjunction=True)
    elif isinstance(node, AllOf):
        for operand in node.operands:
            assert_role_is_decidable(operand, under_disjunction)


@dataclass(frozen=True)
class CompiledScreen:
    where: str
    params: dict
    #: metric -> SELECT expression, 1 when the preference is demonstrated.
    preference_expressions: dict
    order_by: Optional[str] = None
    order_applicable: Optional[str] = None


def compile_screen(criteria: Sequence[Criterion],
                   run_scope: RunScope,
                   order_by: Optional[str] = None,
                   descending: bool = True,
                   dialect: Dialect = "postgres",
                   states_col: str = "metric_states",
                   run_column: str = "compute_run_id") -> CompiledScreen:
    """A whole screen: membership, preference expressions and ranking subset.

    ``run_scope`` is positional and required. A screen compiled without it
    would read legacy rows through a clause that cannot interpret them.
    """
    clauses: list[str] = [run_scope.sql(dialect, run_column)]
    params: dict = {}
    preferences: dict = {}

    for i, criterion in enumerate(criteria):
        param = f"p{i}_{normalise(criterion.metric)}"
        params[param] = criterion.value

        fragment = compile_criterion(criterion, param, dialect, states_col)
        if fragment is not None:
            clauses.append(fragment)
        elif criterion.criterion is CriterionType.PREFERRED:
            applicable = applicable_sql(criterion.metric, dialect, states_col)
            predicate = predicate_sql(criterion, param, dialect)
            preferences[criterion.metric] = (
                f"CASE WHEN {applicable} AND {predicate} THEN 1 ELSE 0 END")

    where = " AND ".join(clauses) if clauses else "TRUE"

    order_sql = order_applicable = None
    if order_by:
        # Ranking participation is separate from universe membership: a
        # company with an unavailable yield stays in the result set and is
        # absent from the yield ordering. Neither dropped nor zeroed.
        order_applicable = applicable_sql(order_by, dialect, states_col)
        direction = "DESC" if descending else "ASC"
        order_sql = f"{column_for(order_by)} {direction}"

    return CompiledScreen(where, params, preferences, order_sql, order_applicable)


def order_participation_sql(order_by: str, dialect: Dialect = "postgres",
                            states_col: str = "metric_states") -> str:
    """A flag a route can select so the UI can say who was left out and why.

    Without it the frontend sees a company present in the result set and
    missing from the ranking, and has no way to distinguish that from a bug.
    """
    return (f"CASE WHEN {applicable_sql(order_by, dialect, states_col)} "
            f"THEN TRUE ELSE FALSE END")


# ── Pagination ────────────────────────────────────────────────────────────────

def paginated_ranking_sql(compiled: CompiledScreen, table: str,
                          select: str, limit: int, offset: int = 0,
                          dialect: Dialect = "postgres") -> str:
    """Top-N over the ranking participants, not over the result set.

    The trap this closes: membership and ranking participation are separated
    correctly, and then LIMIT is applied to a query that still contains the
    non-participants. A company with a source-unhealthy dividend yield does
    not become 0% — it is simply still there, occupying one of the twenty
    slots in "top 20 dividend yields" while sorting wherever the database
    happens to put NULLs. The semantics are locally correct and the customer
    receives nineteen real answers and a hole.

    So the ordering participant clause is part of the WHERE, not a flag on the
    projection, and the limit applies after it.
    """
    if compiled.order_applicable is None:
        raise CompileError(
            "paginated_ranking_sql needs an ORDER BY metric; without one "
            "there is no participant set to paginate over")

    return (f"SELECT {select} FROM {table} "
            f"WHERE {compiled.where} AND {compiled.order_applicable} "
            f"ORDER BY {compiled.order_by} "
            f"LIMIT {int(limit)} OFFSET {int(offset)}")


def excluded_from_ordering_sql(compiled: CompiledScreen, table: str,
                               select: str) -> str:
    """The companies that are in the screen and not in the ranking.

    Returned alongside the page rather than discarded, so a surface can say
    "3 companies could not be ranked on this metric" instead of leaving the
    customer to infer that the universe is smaller than it is.
    """
    if compiled.order_applicable is None:
        raise CompileError("no ORDER BY metric, so nothing is excluded from it")

    return (f"SELECT {select} FROM {table} "
            f"WHERE {compiled.where} AND NOT {compiled.order_applicable}")
