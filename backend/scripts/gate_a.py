"""
Gate A — pre-migration projection containment
=============================================
Proves, against the real database, that no governed observation leaves any
customer-facing surface while there is no validated applicability contract,
and that every governed absence carries an interpretable reason.

Two halves, and the second is the one that catches real defects:

    no governed value is emitted        nothing leaked
    every absence is explained          no blank without a cause

Checking only the first passes a response full of nulls that the client
cannot distinguish from suppressions — which is exactly the state this gate
found on 862907b, where four fields per screener row and eleven per batch row
arrived null because the query never selected them.

This is a release gate, not a report. It exits non-zero on any breach, so it
cannot be discharged by misreading output. Run it from backend/ with the
environment loaded:

    cd /opt/asx-screener/backend && ../asx-venv/bin/python scripts/gate_a.py

Expected only while screener.compute_runs does not exist. Once the migration
and canonical recompute have run, the contract exists and this gate's premise
is gone — Gate B proves the post-recompute behaviour instead.
"""

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.v1.routes.screener import _EXPORT_COLS  # noqa: E402
from app.core.deps import get_current_user  # noqa: E402
from app.core.row_projection import NO_CONTRACT  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.screener import ScreenerRow  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
)
from compute.engine.universe_writer import column_for  # noqa: E402

# A paid user, because the CSV export is gated behind one and an unauthenticated
# 401 would skip the surface rather than prove it.
app.dependency_overrides[get_current_user] = lambda: {"plan": "pro", "id": 1}

GOVERNED = GOVERNED_METRICS[LATEST_MODEL_VERSION]

# Forward map, canonical -> column: the same direction the writer uses. Deriving
# it by inverting column names would make this gate depend on the alias
# machinery it exists to catch failures in.
COL2CANON = {column_for(m): m for m in GOVERNED}
API_GOV = {c: m for c, m in COL2CANON.items() if c in ScreenerRow.model_fields}
CSV_GOV = sorted(set(COL2CANON) & set(_EXPORT_COLS))

FINANCIALS = {"filters": [{"field": "sector", "operator": "eq",
                           "value": "Financials"}],
              "sort_by": "market_cap", "page_size": 3}

breaches: list[str] = []


def check(ok: bool, message: str) -> None:
    if not ok:
        breaches.append(message)


def audit(tag: str, rows) -> None:
    """Both halves, per governed field the surface advertises."""
    # An empty result satisfies every loop below vacuously and prints a clean
    # pass. A gate that proves nothing is worse than one that fails, because
    # it gets believed.
    check(bool(rows), f"{tag}: no rows returned, gate proves nothing")

    for row in rows:
        code = row["asx_code"]
        states = row.get("metric_states", {})
        leaked, unexplained, wrong = {}, [], []

        for column, metric in API_GOV.items():
            if row.get(column) is not None:
                leaked[column] = row[column]

            entry = states.get(metric)
            if entry is None:
                unexplained.append(f"{column}->{metric}")
                continue

            # Blank plus an arbitrary state is not containment. Pre-migration
            # every governed field goes through one withheld path, so all
            # three components are known in advance and asserted exactly.
            if (entry.get("state") != "unavailable"
                    or entry.get("cause") != "source_missing"
                    or entry.get("reason") != NO_CONTRACT):
                wrong.append(f"{metric}={entry}")

            if "observed" in entry:
                breaches.append(f"{tag} {code}: {metric} leaked observed")

        check(not leaked, f"{tag} {code}: LEAKED {leaked}")
        check(not unexplained, f"{tag} {code}: blank without cause {unexplained}")
        check(not wrong, f"{tag} {code}: wrong state {wrong[:3]}")
        print(f"  {tag} {code:5} states={len(states):3} leaked={len(leaked)} "
              f"unexplained={len(unexplained)} wrong={len(wrong)}")


def contract_table_is_readable() -> tuple[bool, str]:
    """Can the APPLICATION read screener.compute_runs, once it exists?

    Gate A asserts a 503 on governed queries, and gets one whether the table
    is missing, empty, or unreadable. That is a hole: after the migration the
    table was owned by postgres while the app connects as another role, so
    every governed query failed with InsufficientPrivilegeError and degraded
    to the same 503 this gate treats as success. A canonical recompute could
    then write a valid run and leave every governed surface unavailable, with
    this gate still reporting PASS.

    So the permission is checked positively, with the credentials the app
    uses. Zero rows is a pass; a permission error is not.

    On its own engine, disposed before returning. Using the application's
    shared AsyncSessionLocal left a pooled connection bound to this probe's
    event loop; TestClient then opened a different loop, checked that
    connection out, and the app's startup DDL failed with "attached to a
    different loop". A gate that breaks part of application startup in order
    to run its own check can hide a real startup failure behind its own.
    """
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    async def _probe() -> tuple[bool, str]:
        # NullPool plus dispose(): nothing survives this call to be checked
        # out later on another loop.
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    text("SELECT 1 FROM screener.compute_runs LIMIT 1"))
            return True, "readable"
        except Exception as exc:                          # noqa: BLE001
            message = str(exc)
            if "does not exist" in message:
                return True, "absent (pre-migration)"
            return False, message.splitlines()[0][:160]
        finally:
            await engine.dispose()

    return asyncio.run(_probe())


def main() -> int:
    readable, detail = contract_table_is_readable()
    check(readable,
          f"the application cannot read screener.compute_runs: {detail}. "
          f"Governed queries would 503 forever and this gate would still pass.")
    print(f"contract table: {detail}")

    check(len(COL2CANON) == len(GOVERNED),
          f"storage-column collision: {len(GOVERNED)} metrics -> "
          f"{len(COL2CANON)} columns")
    print(f"governed: {len(GOVERNED)} canonical, {len(API_GOV)} on ScreenerRow, "
          f"{len(CSV_GOV)} exported")
    # Printed because these are where comparing physical field names against
    # sidecar keys would falsely report an unexplained suppression.
    print("aliases:", {c: m for c, m in API_GOV.items() if c != m} or "none")

    with TestClient(app) as client:
        response = client.post("/api/v1/screener", json=FINANCIALS)
        body = response.json()
        check(response.status_code == 200,
              f"ungoverned screen {response.status_code}, want 200")
        check(body.get("snapshot") is None,
              f"pre-migration snapshot should be null, got {body.get('snapshot')}")
        print("ungoverned screen", response.status_code,
              "snapshot=", body.get("snapshot"))
        audit("screen", body.get("data", []))

        governed = client.post("/api/v1/screener",
                               json={"filters": [],
                                     "sort_by": "grossed_up_yield",
                                     "page_size": 3})
        check(governed.status_code == 503,
              f"governed screen {governed.status_code}, want 503")
        print("governed screen  ", governed.status_code)

        batch = client.post("/api/v1/screener/batch",
                            json={"codes": ["CBA", "BHP"]})
        check(batch.status_code == 200, f"batch {batch.status_code}, want 200")
        print("batch            ", batch.status_code)
        if batch.status_code == 200:
            audit("batch ", batch.json())

        export = client.post("/api/v1/screener/export", json=FINANCIALS)
        check(export.status_code == 200,
              f"csv export {export.status_code}, want 200")
        print("csv export       ", export.status_code)
        if export.status_code == 200:
            # csv.reader, not split(","): a quoted company name containing a
            # comma would shift every index and turn a leak into a false pass.
            # Positions come from _EXPORT_COLS because the header row carries
            # display labels, not column names.
            rows = list(csv.reader(io.StringIO(export.text)))
            index = {name: i for i, name in enumerate(_EXPORT_COLS)}
            check(len(rows) > 1, "csv has no data rows")
            for line in rows[1:4]:
                populated = {g: line[index[g]] for g in CSV_GOV
                             if index[g] < len(line) and line[index[g]].strip()}
                check(not populated,
                      f"csv {line[0]}: governed columns populated {populated}")
                print(f"   csv    {line[0]:5} "
                      f"governed-populated={len(populated)}")

    print()
    if breaches:
        print(f"GATE A FAILED - {len(breaches)} breach(es):")
        for breach in breaches:
            print("  -", breach)
        return 1
    print("GATE A PASSED - pre-migration containment holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
