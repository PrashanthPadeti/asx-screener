"""
The observer must not join the system it observes
=================================================
`docs/canonical_orchestration.md` rule 6:

    An instrument is side-effect-free by default. Importing or exercising
    diagnostic/test code must never instantiate a production execution
    authority. Any external mutation requires an explicit, independently
    attested write-capable mode.

Frozen after the third occurrence, not the first:

    Gate B started nineteen APScheduler jobs on the production host while its
    own docstring said it was read-only, because importing app.main runs the
    lifespan.

    Gate B wrote a screener response into the SERVING Redis. Worse than the
    pollution: a cached body meant a second gate run could assert against a
    response the first run had left behind, and pass because of it.

    test_admin_scheduler_surface started nineteen jobs again. It set
    os.environ["SCHEDULERS_ENABLED"] — but Settings reads the environment once
    at import, another test had already imported app.main, and the freeze
    never took. It passed standalone and failed only under pytest.

That last one is why this module exists in the shape it does.

Read at call time, never at import
----------------------------------
`instrument_mode()` consults os.environ on every call. It deliberately does
NOT cache, and deliberately does not live on the Settings object, because the
whole failure was a flag resolved once at import while the decision to set it
came later. A protection whose correctness depends on import order is not a
protection; it is a coin toss with good intentions.

Writes require an attestation, not a flag
-----------------------------------------
Turning the mode off is not enough to write. `allow_writes()` requires a
second variable naming WHAT is being attested, so "I am allowed to mutate"
cannot be set absent-mindedly by something that only wanted to silence a
refusal.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

#: Set by tests/conftest.py before any application import, and by any
#: diagnostic that imports application code.
INSTRUMENT_ENV = "ASX_INSTRUMENT_MODE"

#: The attestation. Must name the target, e.g. "scratch:asx_screener_scratch".
#: A bare "1" is refused: an attestation that says nothing attests nothing.
WRITE_ATTESTATION_ENV = "ASX_INSTRUMENT_ALLOW_WRITES"

_TRUE = ("1", "true", "yes", "on")


class InstrumentRefused(RuntimeError):
    """Raised when instrument code attempts an unattested external mutation.

    Loud by design. A silent no-op would let a diagnostic believe it had
    written, and the next thing it asserts would be about a world that does
    not exist.
    """


def instrument_mode() -> bool:
    """True when this process is an instrument rather than the application.

    Consulted on every call. See the module docstring for why.
    """
    return os.getenv(INSTRUMENT_ENV, "").strip().lower() in _TRUE


def allow_writes() -> str | None:
    """The attestation for external mutation, or None.

    Returns the attestation TEXT so a refusal message can say what was
    claimed. A value of "1" or "true" is not an attestation — it is the
    absence of one, written confidently — and is rejected.
    """
    value = os.getenv(WRITE_ATTESTATION_ENV, "").strip()
    if not value or value.lower() in _TRUE:
        return None
    return value


def refuse(what: str, *, detail: str = "") -> None:
    """Refuse an external mutation unless it is attested.

    Called by the narrow set of places that can reach outside this process:
    the cache, the mail client, the scheduler bootstrap.
    """
    if not instrument_mode():
        return
    attestation = allow_writes()
    if attestation:
        log.warning("instrument mode: %s permitted under attestation %r",
                    what, attestation)
        return
    raise InstrumentRefused(
        f"{what} refused: this process is running as an instrument "
        f"({INSTRUMENT_ENV} is set) and no write attestation was supplied. "
        f"Set {WRITE_ATTESTATION_ENV} to a value naming what you are "
        f"attesting — e.g. 'scratch:asx_screener_scratch' — if this mutation "
        f"is genuinely intended."
        + (f" ({detail})" if detail else ""))


class NullScheduler:
    """Accepts every scheduler call and schedules nothing.

    Not a mock: it is what an instrument process legitimately has instead of a
    scheduler. add_job returns without registering, start() does nothing, and
    get_jobs() is empty — so a surface that reports "which jobs are
    registered" reports the truth, which is none.

    The alternative — branching at each of twenty add_job call sites — would
    put the protection in the same place the mistake keeps being made.
    """

    def __init__(self) -> None:
        self.refused: list[str] = []

    def add_job(self, func, *args, **kwargs):          # noqa: ANN001
        self.refused.append(str(kwargs.get("id") or getattr(func, "__name__", "?")))
        return None

    def start(self, *args, **kwargs) -> None:
        log.warning("instrument mode: scheduler start suppressed; %d job(s) "
                    "were declared and none registered: %s",
                    len(self.refused), ", ".join(self.refused) or "-")

    def shutdown(self, *args, **kwargs) -> None:
        return None

    def get_jobs(self):
        return []

    def remove_all_jobs(self, *args, **kwargs) -> None:
        return None
