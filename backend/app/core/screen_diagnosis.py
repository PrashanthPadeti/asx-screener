"""
Why a screen returned nothing
=============================
On 30 October 2026 the "Advanced Mining Value Screen" returned 0 stocks. It
was not a strict screen: 44 ASX miners cleared every condition except the
Piotroski F-Score, and the F-Score is not computed for ANY of the 2,113
companies in the universe. Ten of the thirty-one preset screens filtered on
it. Each one had been returning an empty table since it shipped.

Nothing was broken in the data layer. Every company carried an explicit state:

    unavailable    / computation_unsupported   1463
    not_meaningful / domain                     650

The sidecar recorded it, the universe stored it, the API returned it -- and
the page rendered **"0 stocks matched"**, which is what an honest empty result
looks like too. The absence survived four layers and died at the fifth, where
the customer was.

So this module asks the question the page could not: of the criteria in this
screen, is there one that NO company could be evaluated against? That is a
different answer from "nothing matched", and the customer is entitled to it.

Two shapes qualify, and both must be covered:

  governed    the metric has a withholding state in metric_states, with a
              cause and a human reason -- piotroski_f_score, which says
              "leverage-change and current-ratio subtests are out of domain"
  ungoverned  the column is simply NULL for the entire population, with no
              sidecar to explain it -- beta_1y, momentum_3m, short_ratio and
              16 other fields the Field Reference offers for filtering

Checking only the governed half would leave a customer filtering on beta_1y
with exactly the bare zero this exists to remove.

COST. This runs only when a screen returns nothing, and issues at most two
grouped queries over a population the screen has already counted. An
instrument must not consume the resources of the system it observes, so the
criterion list is bounded and the queries carry no joins.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text

#: Criteria examined per diagnosis. A screen with more than this many filters
#: that still returns nothing is explained well enough by the first few, and
#: the bound is what keeps a diagnostic from becoming a load source.
MAX_CRITERIA = 8


def _criterion_fields(parsed) -> list:
    """Every field the screen filters on, in order, de-duplicated.

    Reads Criterion.fields() rather than .field: a field-to-field comparison
    (v11.2.67) names two, and the right-hand one is just as capable of being
    the reason nothing matched.
    """
    seen, out = set(), []
    for criterion in getattr(parsed, "criteria", ()) or ():
        for name in criterion.fields():
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


async def diagnose_empty_screen(db, parsed, registry, where: str,
                                params: dict) -> Optional[list]:
    """Criteria that NO company in scope could be evaluated against.

    Returns None when the emptiness has no such explanation -- which is the
    common, honest case of a screen that is simply strict.
    """
    from app.core.screener_fields import UnknownField, resolve

    fields = _criterion_fields(parsed)[:MAX_CRITERIA]
    if not fields:
        return None

    definitions = {}
    for name in fields:
        try:
            definitions[name] = resolve(registry, name)
        except UnknownField:
            continue            # already refused upstream; not our story
    if not definitions:
        return None

    # One pass: how many rows in scope carry a value for each column. A
    # count() over the screen's own base population, no joins, no ordering.
    selects = ", ".join(
        f"count({d.column}) AS c{i}" for i, d in enumerate(definitions.values()))
    row = (await db.execute(
        text(f"SELECT count(*) AS n, {selects} "
             f"FROM screener.universe u WHERE {where}"), params)).mappings().one()

    population = int(row["n"] or 0)
    if not population:
        return None             # the base population is empty; a different story

    barren = [(name, d) for i, (name, d) in enumerate(definitions.items())
              if not int(row[f"c{i}"] or 0)]
    if not barren:
        return None

    out = []
    for name, definition in barren:
        entry: dict[str, Any] = {
            "field":     name,
            "label":     definition.label or name,
            "metric":    definition.canonical,
            "state":     None,
            "cause":     None,
            "reason":    None,
            "affected":  population,
            "universe":  population,
        }
        if definition.canonical:
            # The governed half: ask the sidecar why, and take the reason the
            # most companies share rather than inventing a summary.
            detail = (await db.execute(
                text(f"""
                    SELECT u.metric_states -> :m ->> 'state'  AS state,
                           u.metric_states -> :m ->> 'cause'  AS cause,
                           u.metric_states -> :m ->> 'reason' AS reason,
                           count(*) AS n
                    FROM screener.universe u
                    WHERE {where}
                    GROUP BY 1, 2, 3
                    ORDER BY n DESC
                    LIMIT 1
                """), {**params, "m": definition.canonical})).mappings().first()
            if detail and detail["state"]:
                entry.update(state=detail["state"], cause=detail["cause"],
                             reason=detail["reason"],
                             affected=int(detail["n"] or population))
        out.append(entry)
    return out or None
