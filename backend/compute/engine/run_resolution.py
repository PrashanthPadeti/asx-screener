"""
Which finalised runs may be served
==================================
One definition, shared by the API resolver and by anything that needs to ask
the same question outside a request — the rehearsal's adversarial assertions,
most immediately.

It lives here rather than in the route because a second copy is the failure it
would be used to detect. An assertion bundle with its own idea of "servable"
can report that the resolver refuses a failed run while the resolver, reading a
different query, serves it.

The rule, unchanged: a run is servable when it is finalised, carries no
persistence violations, was computed under a factor model this build can
interpret, and has a SUCCESS stage row for every stage the plan IT WAS OPENED
UNDER requires. Requirements come from the run's own immutable plan_name --
never one static list, which is what hid every DAILY_CANONICAL run.

No psycopg2 or SQLAlchemy import here: the API reaches this through SQLAlchemy
and the harness through psycopg2, and this module must be importable by both.
"""

from __future__ import annotations

import json

#: Parameters: :supported (text[]), :plan_requirements (jsonb), :limit.
#:
#: The join to plan_requirements is INNER, deliberately. A run whose plan_name
#: this build cannot look up is not served: an unrecognised plan is a
#: publication contract nobody can evaluate, and serving it would mean trusting
#: evidence against requirements no one can name.
VALIDATED_RUNS_SQL = """
    WITH plan_requirements AS (
        SELECT key AS plan_name,
               ARRAY(SELECT jsonb_array_elements_text(value)) AS required
          FROM jsonb_each(CAST(:plan_requirements AS jsonb))
    )
    SELECT r.id, r.factor_model_version, r.unhealthy_sources, r.detail
      FROM screener.compute_runs r
      JOIN screener.compute_run_finalizations f ON f.run_id = r.id
      JOIN plan_requirements pr ON pr.plan_name = r.plan_name
     WHERE r.factor_model_version = ANY(:supported)
       AND f.persistence_violations = 0
       AND NOT EXISTS (
           SELECT 1 FROM unnest(pr.required) AS req(name)
            WHERE NOT EXISTS (
                SELECT 1 FROM screener.compute_run_stages s
                 WHERE s.run_id     = r.id
                   AND s.stage_name = req.name
                   AND s.status     = 'success'))
     ORDER BY r.run_at DESC
     LIMIT :limit
"""

#: The same statement with psycopg2's placeholders. Derived from the one above
#: by substitution rather than written out again, so the two cannot drift.
_PSYCOPG_SUBS = {":plan_requirements": "%(plan_requirements)s",
                 ":supported": "%(supported)s",
                 ":limit": "%(limit)s"}


def validated_runs_sql_psycopg() -> str:
    sql = VALIDATED_RUNS_SQL
    for named, positional in _PSYCOPG_SUBS.items():
        sql = sql.replace(named, positional)
    return sql


def validated_run_ids(cur, limit: int = 8) -> list[int]:
    """The run ids the API would serve, asked synchronously.

    Same statement, same parameters, same answer as a governed request would
    get — which is the only reason an assertion about "the resolver" means
    anything.
    """
    from compute.engine.metric_states import GOVERNED_METRICS
    from compute.engine.run_plans import plan_requirements

    cur.execute(validated_runs_sql_psycopg(),
                {"supported": list(GOVERNED_METRICS.keys()),
                 "plan_requirements": json.dumps(plan_requirements()),
                 "limit": limit})
    return [r[0] for r in cur.fetchall()]
