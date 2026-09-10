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

    field: str                       # the resolved field key, not a column
    role: CriterionType
    operator: str
    value: Any
    kind: str = "number"             # number | text | boolean
    #: Resolved after parsing. None for an ungoverned field, which keeps its
    #: existing deterministic behaviour rather than acquiring P0-A semantics.
    canonical: Optional[str] = None
    governed: bool = False

    def resolved(self, definition: FieldDef) -> "Criterion":
        return Criterion(self.field, self.role, self.operator, self.value,
                         self.kind, definition.canonical, definition.governed)

    def fields(self) -> tuple[str, ...]:
        return (self.field,)


# ── The expression tree ───────────────────────────────────────────────────────
# The existing parser already builds a real AST — _ConditionNode, _AndNode,
# _OrNode, with proper precedence and parentheses — so the language can express
# (A AND B) OR C. Flattening that into a list of criteria would silently
# discard the grouping and turn a disjunction into a conjunction, which is a
# wrong answer rather than a lost convenience. The tree is preserved.

@dataclass(frozen=True)
class AllOf:
    """Every operand must hold."""

    operands: tuple = ()

    def fields(self) -> tuple[str, ...]:
        return tuple(f for o in self.operands for f in o.fields())


@dataclass(frozen=True)
class AnyOf:
    """At least one operand must hold."""

    operands: tuple = ()

    def fields(self) -> tuple[str, ...]:
        return tuple(f for o in self.operands for f in o.fields())


def walk(node) -> list:
    """Every Criterion in a tree, in source order.

    For inspecting *which* fields a query touches — governance, run scope,
    validation. Never for evaluating it: reading the leaves and ignoring the
    branches is exactly the flattening the tree exists to prevent.
    """
    if isinstance(node, Criterion):
        return [node]
    if isinstance(node, (AllOf, AnyOf)):
        return [c for operand in node.operands for c in walk(operand)]
    return []


def map_criteria(node, fn):
    """Rebuild a tree with every Criterion transformed, structure intact."""
    if isinstance(node, Criterion):
        return fn(node)
    if isinstance(node, AllOf):
        return AllOf(tuple(map_criteria(o, fn) for o in node.operands))
    if isinstance(node, AnyOf):
        return AnyOf(tuple(map_criteria(o, fn) for o in node.operands))
    return node


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

    #: The whole condition, grouping preserved. None means no filters.
    expression: Optional[Any] = None
    ordering: Optional[Ordering] = None
    raw: str = ""

    @property
    def criteria(self) -> tuple[Criterion, ...]:
        """Every leaf, for inspection only — the tree is what compiles."""
        return tuple(walk(self.expression))

    @property
    def governed_criteria(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if c.governed)

    @property
    def ungoverned_criteria(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if not c.governed)

    @property
    def requires_run_scope(self) -> bool:
        """True when any semantic consumer of governed data is present.

        Filters, ordering and eventually preferences alike — not only the
        WHERE criteria. A query with no filters at all that ranks by a
        governed metric still needs the contract, and a filter-only check
        would miss it.
        """
        return bool(self.governed_criteria) or bool(
            self.ordering and self.ordering.governed)


def canonicalise(parsed: ParsedQuery,
                 registry: Mapping[str, FieldDef]) -> ParsedQuery:
    """Attach canonical identity and governance to every field reference.

    Runs immediately after parsing and before any compilation, so no later
    stage has to guess whether ``ev_to_ebitda`` and ``ev_ebitda`` are the same
    concept. Unknown fields raise here rather than at the database.
    """
    expression = map_criteria(
        parsed.expression, lambda c: c.resolved(resolve(registry, c.field)))

    ordering = parsed.ordering
    if ordering is not None:
        definition = resolve(registry, ordering.field, for_sort=True)
        ordering = Ordering(ordering.field, ordering.direction,
                            definition.canonical, definition.governed)

    return ParsedQuery(expression, ordering, parsed.raw)


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
    params: dict = {}
    counter = [0]

    def render(node) -> str:
        if isinstance(node, AllOf):
            if not node.operands:
                return "TRUE"
            return " AND ".join(f"({render(o)})" for o in node.operands)
        if isinstance(node, AnyOf):
            if not node.operands:
                return "FALSE"
            return " OR ".join(f"({render(o)})" for o in node.operands)

        definition = resolve(registry, node.field)
        operator = OPERATOR_SQL.get(node.operator)
        if operator is None:
            raise UnknownField(f"unsupported operator: {node.operator!r}")

        if node.kind == "boolean":
            want_true = node.value if operator == "=" else not node.value
            clause = (f"({definition.column})::int != 0" if want_true
                      else f"({definition.column})::int = 0")
        else:
            key = f"{prefix}{counter[0]}"
            counter[0] += 1
            value = node.value
            if definition.type == "number":
                value = float(value) * definition.scale
            params[key] = value
            clause = f"({definition.column}) {operator} :{key}"

        if node.role is CriterionType.EXCLUDED:
            clause = f"NOT ({clause})"
        return clause

    if parsed.expression is None:
        return "TRUE", {}
    return render(parsed.expression), params
