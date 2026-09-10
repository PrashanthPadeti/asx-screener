"""
One canonical field definition
==============================
``routes/screener.py`` carries two maps: ``ALLOWED_FIELDS`` (309 entries, API
name -> physical column and type) and ``SORTABLE_COLS`` (163 entries, API name
-> physical column). They agree today — checked, zero column disagreements —
but they agree by discipline rather than by construction, and a third consumer
was about to be added.

So one definition carrying everything a caller needs to decide:

    physical column      where it lives
    canonical identity   what it means, where the contract governs it
    governed             whether P0-A applicability applies
    filterable/sortable  what a request may ask of it

Deriving the registry from the existing maps rather than retyping 309 entries
keeps this mechanical: there is no opportunity to mistype a column while
"tidying". The drift the two maps could have developed is closed by
construction, and a test asserts the derivation is faithful to both.

Governed and ungoverned fields are deliberately both here. P0-A does not
apply to all 309 — a governed field goes through canonical identity and the
run contract, an ungoverned one keeps its existing deterministic behaviour,
and the registry is where a caller learns which it is holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from compute.engine.metric_registry import normalise
from compute.engine.metric_states import GOVERNED_METRICS, LATEST_MODEL_VERSION


class UnknownField(Exception):
    """A field name no request may use.

    Raised rather than defaulted. The route previously resolved an unknown
    ``sort_by`` to ``market_cap``, which silently re-sorted the page by
    something the caller never asked for — a wrong answer presented as an
    ordinary one.
    """


@dataclass(frozen=True)
class FieldDef:
    """Everything a request needs to know about one screener field."""

    key: str
    column: str                      # physical, e.g. "u.ev_to_ebitda"
    type: str                        # number | text | boolean
    scale: float = 1.0
    label: str = ""
    unit: str = ""
    category: str = ""
    filterable: bool = True
    sortable: bool = False
    #: The canonical metric identity, where one exists. Note this is not the
    #: key: the key is an API name and may be a storage spelling.
    canonical: Optional[str] = None
    governed: bool = False

    @property
    def bare_column(self) -> str:
        """The column without its table alias, for ORDER BY over a subquery."""
        return self.column.split(".")[-1]


def build_registry(allowed_fields: Mapping[str, Mapping],
                   sortable_cols: Mapping[str, str],
                   model_version: str = LATEST_MODEL_VERSION
                   ) -> dict[str, FieldDef]:
    """Derive one registry from the two maps the route carries today."""
    governed = GOVERNED_METRICS[model_version]
    out: dict[str, FieldDef] = {}

    for key, info in allowed_fields.items():
        canonical = normalise(key)
        out[key] = FieldDef(
            key=key,
            column=info["col"],
            type=info.get("type", "number"),
            scale=float(info.get("scale", 1.0) or 1.0),
            label=info.get("label", ""),
            unit=info.get("unit", ""),
            category=info.get("cat", ""),
            filterable=True,
            sortable=key in sortable_cols,
            canonical=canonical if canonical in governed else None,
            governed=canonical in governed,
        )

    # Sortable-only fields — asx_code and company_name are orderable identity
    # columns nobody filters on.
    for key, column in sortable_cols.items():
        if key in out:
            continue
        canonical = normalise(key)
        out[key] = FieldDef(
            key=key, column=column, type="text", filterable=False,
            sortable=True,
            canonical=canonical if canonical in governed else None,
            governed=canonical in governed)

    return out


def resolve(registry: Mapping[str, FieldDef], name: str,
            *, for_sort: bool = False) -> FieldDef:
    """Look up a field, or refuse. Never a default.

    ``for_sort`` distinguishes the two refusals so the caller can say which
    capability was missing rather than only that the name was wrong.
    """
    field = registry.get((name or "").strip().lower())
    if field is None:
        raise UnknownField(f"unknown field: {name!r}")

    if for_sort and not field.sortable:
        raise UnknownField(
            f"{name!r} is not sortable; it can be filtered on but has no "
            f"deterministic ordering defined")
    if not for_sort and not field.filterable:
        raise UnknownField(f"{name!r} cannot be used as a filter")

    return field


def governed_fields(registry: Mapping[str, FieldDef]) -> dict[str, FieldDef]:
    """The subset P0-A applicability applies to."""
    return {k: f for k, f in registry.items() if f.governed}
