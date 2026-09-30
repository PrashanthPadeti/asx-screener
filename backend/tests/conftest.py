"""
Instrument mode, set before anything can import the application
===============================================================
pytest imports `conftest.py` before it collects or imports any test module,
so this is the earliest point at which the whole suite can be declared an
instrument. That timing is the entire point.

The incident this exists to prevent
-----------------------------------
`test_admin_scheduler_surface` set `os.environ["SCHEDULERS_ENABLED"] = "false"`
inside the test body. It passed when run alone and failed under pytest —
because another test had already imported `app.main`, `Settings` reads the
environment once at import, and the assignment arrived after the value had
been resolved. `frozen` was False, the TestClient lifespan ran, and nineteen
real APScheduler jobs were registered and started on the host.

Two lessons, both encoded here:

    the flag must be set before ANY application import, which means here and
    not in a test body;

    and the flag must be read at CALL time, which is why
    `app.core.instrument.instrument_mode()` consults os.environ every time
    rather than caching or living on Settings.

Either alone is insufficient. A late-set flag read at call time still fails
for anything that ran before it; an early-set flag read at import time is
fine until an import order changes.

What instrument mode does NOT do
--------------------------------
It does not make tests pass. It removes this process's ability to start a
scheduler, write the serving cache or send mail. A test that needs a real
external mutation must attest to it explicitly — see
`ASX_INSTRUMENT_ALLOW_WRITES` — and say what it is attesting.
"""

import os
import sys
from pathlib import Path

# Before the imports below, and before pytest collects anything.
os.environ.setdefault("ASX_INSTRUMENT_MODE", "1")

# Deliberately NOT setting ASX_INSTRUMENT_ALLOW_WRITES. The suite has no
# business mutating anything outside its own process, and a default
# attestation would make the refusal unreachable — which is how a protection
# becomes decorative.

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def pytest_report_header(config):                        # noqa: ANN001, ARG001
    """Say it out loud in the run header.

    A protection nobody can see in the output is one nobody notices has
    stopped working.
    """
    from app.core.instrument import allow_writes, instrument_mode
    return (f"instrument mode: {instrument_mode()}; "
            f"write attestation: {allow_writes() or 'none'}")
