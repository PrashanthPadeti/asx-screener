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

    if criterion.criterion is CriterionType.REQUIRED:
        # The requirement must be *proven*, so both halves must hold.
        return f"({applicable} AND {predicate})"

    if criterion.criterion is CriterionType.EXCLUDED:
        # The exclusion must be proven to reject. Unproven leaves the row in.
        return f"NOT ({applicable} AND {predicate})"

    return None


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
