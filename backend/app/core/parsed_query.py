"""
The typed query representation
==============================
``parse_query`` returns ``(where_fragment, params)``. Once it has emitted SQL
the meaning is already gone: there is no object saying which criteria were
REQUIRED and which EXCLUDED, no canonical metric identity, no applicability
semantics, and nowhere to record that a criterion could not be evaluated. A
governed pre-pass over the fragment would have to parse SQL to recover
concepts the parser knew a moment earlier and threw away.

So the parser's canonical output becomes a typed object, and SQL is compiled
from it:

    natural language / saved query
      -> typed criteria
      -> canonical metric identity
      -> validated RunScope
      -> single screener builder
      -> SQL + response semantics

**The compatibility direction is one-way.** ``to_legacy_sql`` exists so the
four product paths can migrate one at a time rather than in a flag day, and it
compiles *typed representation -> legacy fragment*. Nothing goes the other
way: inferring typed semantics from an SQL string is the thing this module
exists to stop. The adapter is deleted once nothing calls it.

The parser does not need to know that ``ev_ebitda`` physically lives in
``u.ev_to_ebitda``. Canonicalisation happens immediately after parsing;
storage translation happens at compilation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from app.core.screener_fields import FieldDef, UnknownField, resolve
from compute.engine.metric_registry import normalise
from compute.engine.screen_predicates import CriterionType


class Direction(str, Enum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class Criterion:
    """One condition, in semantic terms rather than SQL terms."""

    field: str                       # the name as written by the user
    role: CriterionType
    operator: str
    value: Any
    #: Resolved after parsing. None for an ungoverned field, which keeps its
    #: existing deterministic behaviour rather than acquiring P0-A semantics.
    canonical: Optional[str] = None
    governed: bool = False

    def resolved(self, definition: FieldDef) -> "Criterion":
        return Criterion(self.field, self.role, self.operator, self.value,
                         definition.canonical, definition.governed)


@dataclass(frozen=True)
class Ordering:
    """What the result is ranked by, separately from what it contains."""

    field: str
    direction: Direction = Direction.DESC
    canonical: Optional[str] = None
    governed: bool = False


@dataclass(frozen=True)
class ParsedQuery:
    """The canonical output of parsing, whatever the input language was.

    A saved screen persists *this*, not the text that produced it and not the
    SQL it compiles to. Replaying a saved query then re-runs a decision rather
    than re-running a string through a parser that may since have changed.
    """

    criteria: tuple[Criterion, ...] = ()
    ordering: Optional[Ordering] = None
    raw: str = ""

    @property
    def governed_criteria(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if c.governed)

    @property
    def ungoverned_criteria(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if not c.governed)

    @property
    def requires_run_scope(self) -> bool:
        """True when anything in the query needs the applicability contract."""
        return bool(self.governed_criteria) or bool(
            self.ordering and self.ordering.governed)


def canonicalise(parsed: ParsedQuery,
                 registry: Mapping[str, FieldDef]) -> ParsedQuery:
    """Attach canonical identity and governance to every field reference.

    Runs immediately after parsing and before any compilation, so no later
    stage has to guess whether ``ev_to_ebitda`` and ``ev_ebitda`` are the same
    concept. Unknown fields raise here rather than at the database.
    """
    criteria = tuple(c.resolved(resolve(registry, c.field))
                     for c in parsed.criteria)

    ordering = parsed.ordering
    if ordering is not None:
        definition = resolve(registry, ordering.field, for_sort=True)
        ordering = Ordering(ordering.field, ordering.direction,
                            definition.canonical, definition.governed)

    return ParsedQuery(criteria, ordering, parsed.raw)


# ── The one-way adapter ───────────────────────────────────────────────────────

OPERATOR_SQL = {
    "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "eq": "=", "ne": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<=",
    "=": "=", "!=": "<>",
}


def to_legacy_sql(parsed: ParsedQuery,
                  registry: Mapping[str, FieldDef],
                  prefix: str = "q") -> tuple[str, dict]:
    """Compile a typed query into the old ``(where_fragment, params)`` shape.

    TEMPORARY, and one-way. It exists so the four product paths can migrate
    individually instead of in a single risky change, and it must be deleted
    when the last caller is gone. It does not and will not have an inverse:
    recovering typed semantics from an SQL string is precisely the loss this
    module was written to prevent.

    Governed criteria compiled through here carry no applicability semantics —
    that is the point of the migration, and a caller still using this adapter
    for a governed field is knowingly on the old path.
    """
    clauses: list[str] = []
    params: dict = {}

    for i, criterion in enumerate(parsed.criteria):
        definition = resolve(registry, criterion.field)
        operator = OPERATOR_SQL.get(criterion.operator)
        if operator is None:
            raise UnknownField(f"unsupported operator: {criterion.operator!r}")

        key = f"{prefix}{i}"
        value = criterion.value
        if definition.type == "number":
            value = float(value) * definition.scale

        clause = f"({definition.column}) {operator} :{key}"
        if criterion.role is CriterionType.EXCLUDED:
            clause = f"NOT {clause}"

        clauses.append(clause)
        params[key] = value

    return (" AND ".join(clauses) if clauses else "TRUE"), params
