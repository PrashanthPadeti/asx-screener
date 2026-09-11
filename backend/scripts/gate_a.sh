#!/usr/bin/env bash
#
# Gate A runner — unit suite, containment gate, then schema evidence.
#
# Lives in the repo rather than being pasted, because a long heredoc through a
# wrapped console has twice produced a corrupted or wrong-tree run. Run it from
# the backend/ directory of a checkout at the commit you intend to prove:
#
#     cd /tmp/p0a-gate/backend && bash scripts/gate_a.sh 2>&1 | tee /tmp/gate.log
#
# The evidence queries always run, even when the gate fails, because what the
# storage schema holds is what decides the post-migration work either way.
# Exits with the gate's status so it is executable truth, not a report.

set -u

ASX_ROOT=${ASX_ROOT:-/opt/asx-screener}
PYBIN=${PYBIN:-$ASX_ROOT/asx-venv/bin/python}

# This gate is specific to the ASX screener. It has been pointed at the wrong
# host once; failing here is cheaper than a confusing run somewhere else.
if [ ! -x "$PYBIN" ]; then
    echo "ERROR: $PYBIN not found — is this the ASX screener host?" >&2
    echo "       hostname: $(hostname)" >&2
    exit 2
fi
if [ ! -f "$ASX_ROOT/backend/.env" ]; then
    echo "ERROR: $ASX_ROOT/backend/.env not found" >&2
    exit 2
fi

set -a; . "$ASX_ROOT/backend/.env"; set +a

echo "HOST:            $(hostname)"
echo "HEAD UNDER TEST: $(git log --oneline -1 2>/dev/null || echo 'not a checkout')"

echo
echo "=== unit suite ==="
suite_failed=0
for t in tests/test_*.py; do
    printf '%-48s' "$(basename "$t")"
    if "$PYBIN" "$t" >/tmp/gate-unit.log 2>&1; then
        tail -1 /tmp/gate-unit.log
    else
        suite_failed=1
        echo "FAIL"
        grep -E "^  (FAIL|ERROR)" /tmp/gate-unit.log || tail -8 /tmp/gate-unit.log
    fi
done

echo
echo "=== GATE A: pre-migration containment ==="
"$PYBIN" scripts/gate_a.py
gate=$?

echo
echo "=== governed columns that exist in screener.universe ==="
sudo -u postgres psql -tAc "
    SELECT column_name FROM information_schema.columns
     WHERE table_schema='screener' AND table_name='universe'
       AND column_name IN ('net_debt_to_ebitda','working_capital',
           'interest_coverage','asset_turnover','roic','composite_score',
           'value_score','quality_score','growth_score','momentum_score',
           'income_score')
     ORDER BY 1;" | tr '\n' ' '
echo

echo
echo "=== populated? (active rows) ==="
sudo -u postgres psql -c "
    SELECT count(*) AS rows,
           count(interest_coverage)  AS int_cov,
           count(working_capital)    AS work_cap,
           count(net_debt_to_ebitda) AS nd_ebitda,
           count(asset_turnover)     AS asset_t,
           count(roic)               AS roic,
           count(composite_score)    AS composite,
           count(value_score)        AS value,
           count(quality_score)      AS quality,
           count(growth_score)       AS growth,
           count(momentum_score)     AS momentum,
           count(income_score)       AS income
      FROM screener.universe WHERE status='active';"

echo "=== governed metrics not exposed on ScreenerRow ==="
"$PYBIN" - <<'PY'
from compute.engine.metric_states import GOVERNED_METRICS, LATEST_MODEL_VERSION
from compute.engine.universe_writer import column_for
from app.schemas.screener import ScreenerRow

columns = {column_for(m) for m in GOVERNED_METRICS[LATEST_MODEL_VERSION]}
print(sorted(columns - set(ScreenerRow.model_fields)))
PY

echo
echo "unit suite:  $([ $suite_failed -eq 0 ] && echo PASS || echo FAIL)"
echo "gate A exit: $gate"
exit $gate
