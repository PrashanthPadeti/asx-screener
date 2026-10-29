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

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from app.core.screener_fields import FieldDef, UnknownField, resolve
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

    #: Set when the right-hand side is another FIELD rather than a literal, as
    #: in ``total_equity > total_debt``. ``value`` is then meaningless and is
    #: None; ``rhs_field`` is the discriminator, not a flag beside it, so the
    #: two states cannot disagree.
    #:
    #: ``fields()`` has always returned a tuple precisely so a criterion could
    #: name more than one field. This is the first thing that does.
    rhs_field: Optional[str] = None
    rhs_canonical: Optional[str] = None
    rhs_governed: bool = False

    @property
    def is_comparison(self) -> bool:
        """True when both sides are fields."""
        return self.rhs_field is not None

    @property
    def touches_governed(self) -> bool:
        """Either side. A one-sided check reads a governed RHS as ungoverned."""
        return self.governed or self.rhs_governed

    def resolved(self, definition: FieldDef,
                 rhs_definition: Optional[FieldDef] = None) -> "Criterion":
        if self.rhs_field is not None and rhs_definition is None:
            raise UnknownField(
                f"criterion compares '{self.field}' against "
                f"'{self.rhs_field}' but only the left side was resolved; "
                f"both sides carry their own governance")
        return Criterion(
            self.field, self.role, self.operator, self.value, self.kind,
            definition.canonical, definition.governed,
            self.rhs_field,
            rhs_definition.canonical if rhs_definition else None,
            rhs_definition.governed if rhs_definition else False)

    def fields(self) -> tuple[str, ...]:
        if self.rhs_field is None:
            return (self.field,)
        return (self.field, self.rhs_field)


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
        # touches_governed, not governed: a criterion whose RIGHT side is a
        # governed metric needs the run contract just as much as one whose
        # left side is, and reading only the left would resolve no scope for
        # it.
        return tuple(c for c in self.criteria if c.touches_governed)

    @property
    def ungoverned_criteria(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if not c.touches_governed)

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
    def _resolve_both(c: Criterion) -> Criterion:
        return c.resolved(
            resolve(registry, c.field),
            resolve(registry, c.rhs_field) if c.rhs_field else None)

    expression = map_criteria(parsed.expression, _resolve_both)

    ordering = parsed.ordering
    if ordering is not None:
        definition = resolve(registry, ordering.field, for_sort=True)
        ordering = Ordering(ordering.field, ordering.direction,
                            definition.canonical, definition.governed)

    return ParsedQuery(expression, ordering, parsed.raw)


# ── Field-to-field comparison: what is not yet supported ─────────────────────

class ComparisonUnsupported(Exception):
    """A field-to-field comparison this build cannot answer correctly.

    Raised rather than degraded. A governed metric answers three ways --
    true, false, and "not applicable to this company, for this reason" -- and
    a comparison of two governed metrics has two such verdicts to combine.
    Compiling it as an ordinary SQL comparison would answer with two of the
    three states and discard the third silently, which is the defect class
    the applicability contract exists to prevent, reappearing in a new
    surface.

    So the capability is absent, and says so, instead of being present and
    wrong. Removing this refusal is Stage 2: ``three_valued_sql`` carrying
    APPLICABLE(lhs) AND APPLICABLE(rhs) AND (lhs op rhs), with the
    withholding reason naming whichever side was unavailable.
    """


def assert_comparison_is_ungoverned(lhs: FieldDef, rhs: FieldDef) -> None:
    """Refuse a comparison that names a governed metric on either side."""
    offending = [d.key for d in (lhs, rhs) if d.governed]
    if not offending:
        return
    raise ComparisonUnsupported(
        f"comparing two fields is not yet available for governed metrics "
        f"({', '.join(offending)}). A governed metric can be inapplicable to "
        f"a company rather than merely above or below a threshold, and this "
        f"build cannot combine two such verdicts. Compare against a number "
        f"instead, or use two separate conditions.")


# ── The one-way adapter ───────────────────────────────────────────────────────

# The legacy compiler's operator map. It knew `ne` and not `neq` -- the same
# gap that made every "≠" filter reach Postgres as the literal word `neq` and
# 500, fixed in screen_sql.py in v11.2.29 and missed HERE because nothing
# compared the two maps. Query Mode then began emitting `neq` (its parser
# translates `!=` to a canonical name) and this raised
# `unsupported operator: 'neq'`.
#
# test_the_two_compilers_accept_the_same_operators now holds them in
# agreement, so a name added to one and not the other fails the gate instead
# of a customer's query.
OPERATOR_SQL = {
    "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "eq": "=", "ne": "<>", "neq": "<>",
    ">": ">", ">=": ">=", "<": "<", "<=": "<=",
    "=": "=", "!=": "<>", "<>": "<>",
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

        if node.rhs_field is not None:
            rhs = resolve(registry, node.rhs_field)
            # The governed exemption above covers criteria that already
            # compiled through this adapter before P0-A existed. A capability
            # added AFTER it does not inherit that exemption: a governed
            # comparison has two applicability verdicts and this path can
            # express neither, so it refuses rather than answering.
            assert_comparison_is_ungoverned(definition, rhs)
            clause = f"({definition.column}) {operator} ({rhs.column})"
        elif node.kind == "boolean":
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
