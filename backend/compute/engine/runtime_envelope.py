"""
Where did this process actually connect?
========================================
An inherited environment is evidence of intent. A live connection answering
``asx_screener_scratch`` is evidence of fact. The orchestrators spawn children
with ``subprocess.run``, and several of those children re-read ``.env``, build
their own URLs, or connect independently — so a redirect proven once in the
parent proves nothing about what any child reached.

This is the gate every write-producing stage passes immediately before its
first mutation.

Why it covers more than PostgreSQL
----------------------------------
discovery-15 ran cleanly against the scratch database, its production sentinel
was unchanged, and it flushed **production** Redis:

    Cache invalidated: 2 asx:screener:* keys flushed

The database redirect held perfectly. The second isolation dimension had no
redirect at all, because ``_flush_screener_cache`` reads ``REDIS_URL`` straight
from the environment and the discovery harness never set it. Harmless that time
— a cache flush costs a recompute — but it proves the rehearsal boundary is the
**execution context**, not the database.

So the envelope reports every authority a stage holds, and refuses the run when
any of them still points at production while the database does not.

Discovery mode
--------------
Set ``P0A_EXPECTED_DB``. The envelope then REFUSES any database but that one,
and requires Redis to be redirected or disabled. Unset — which is production —
it records the envelope and permits everything, so wiring this into a producer
cannot break the nightly pipeline.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

EXPECTED_DB_VAR = "P0A_EXPECTED_DB"
#: Set by the discovery harness to a logical Redis database that production
#: does not use, or to the literal "disabled".
DISCOVERY_REDIS_VAR = "P0A_REDIS_MODE"

#: Must read exactly "enabled". Not a truthiness test: "0", "false" and "no"
#: are all truthy strings, and a variable whose mere presence arms fault
#: injection is a variable that arms it by accident.
DISCOVERY_MODE_VAR = "P0A_DISCOVERY_MODE"
#: The production database name, declared by the harness. The child cannot
#: work it out for itself -- its own DATABASE_URL points at scratch, which is
#: the whole point -- so "scratch is not production" has to be told to it, and
#: an absent declaration is a refusal rather than a pass.
PRODUCTION_DB_VAR = "P0A_PRODUCTION_DB"
#: Which fault to inject, from FAULT_POINTS. Set by p0a_discovery.sh only.
FAULT_VAR = "P0A_DISCOVERY_FAULT"

#: The database's own attestation that it is a rehearsal clone.
#:
#: Every other condition is a claim made BY the environment ABOUT the database.
#: Declarations can contradict each other, and the dangerous combination is a
#: consistent set of lies: P0A_EXPECTED_DB naming production, the live
#: connection agreeing because it really did reach production, and
#: P0A_PRODUCTION_DB naming something else entirely. Nothing in the
#: environment catches that, because everything in the environment is what is
#: wrong.
#:
#: A name denylist would be the obvious fix and is weaker than it looks: this
#: repository is public and production's database name lives only in the
#: server's .env, so a hardcoded guess would be an inert guard the day it is
#: wrong -- and silently inert, which is the worst kind.
#:
#: So the database attests for itself. p0a_discovery.sh writes this table into
#: the scratch clone, recording the name it was created under; the check
#: requires the marker to name the database the connection actually reached.
#: Production has no such table, cannot be given one by any environment
#: variable, and a clone restored somewhere else carries a marker naming the
#: database it came from rather than the one it now is.
SCRATCH_MARKER = "screener.p0a_scratch_marker"

#: Every fault the rehearsal may request. A fixed allowlist, so a typo is a
#: refusal rather than a silently absent fault that makes the adversarial case
#: pass by not happening.
FAULT_POINTS = frozenset({
    #: Between a committed provisional universe rebuild and the canonical
    #: tail. The exact boundary where the temporal guarantee is vulnerable:
    #: the old canonical claim has been revoked and the new one not yet made.
    "after_provisional_rebuild",
})


class EnvelopeRefused(RuntimeError):
    """The process reached something it was not permitted to reach."""


class InjectedFault(RuntimeError):
    """A rehearsal fault fired. Not a defect -- the rehearsal asked for it."""


@dataclass
class Envelope:
    """Every authority this process holds, as observed rather than configured."""

    stage: str
    database: str = ""
    redis_endpoint: str = "not configured"
    redis_logical_db: Optional[str] = None
    discovery: bool = False
    expected_db: Optional[str] = None
    filesystem_roots: list[str] = field(default_factory=list)
    #: What the connected database says about ITSELF: the database name
    #: recorded in its scratch marker, or None if it carries no marker.
    #: Observed, never declared -- see SCRATCH_MARKER.
    scratch_marker: Optional[str] = None

    def lines(self) -> list[str]:
        mode = "DISCOVERY" if self.discovery else "production"
        return [
            f"runtime envelope [{mode}] — {self.stage}",
            f"  postgres  : {self.database}",
            f"  redis     : {self.redis_endpoint}"
            + (f"  (logical db {self.redis_logical_db})"
               if self.redis_logical_db is not None else ""),
            f"  fs roots  : {', '.join(self.filesystem_roots) or '-'}",
        ]


def _redis_url() -> Optional[str]:
    """Both Redis paths read this variable.

    app/core/cache.py reads settings.REDIS_URL (pydantic, environment wins
    over .env) and build_screener_universe reads os.getenv("REDIS_URL")
    directly. One variable, so one redirect covers reads and writes — which is
    why the harness redirects the logical database rather than special-casing
    the one delete call we happened to find.
    """
    return os.getenv("REDIS_URL")


def observe(stage: str, conn=None, *, cursor=None,
            filesystem_roots: Optional[list[str]] = None) -> Envelope:
    """Ask the live connection what it reached. Never infer from the URL.

    ``conn`` or ``cursor`` must be the one the caller is about to write
    through. Reading the URL the caller *meant* to use would reproduce the
    defect this exists to prevent.
    """
    env = Envelope(
        stage=stage,
        expected_db=os.getenv(EXPECTED_DB_VAR) or None,
        filesystem_roots=filesystem_roots or [],
    )
    env.discovery = env.expected_db is not None

    if cursor is None and conn is not None:
        cursor = conn.cursor()
        owned = True
    else:
        owned = False
    if cursor is not None:
        cursor.execute("SELECT current_database()")
        env.database = cursor.fetchone()[0]

        # Probed only when a fault is requested. The marker exists for the
        # fault gate, and asking for it on every production run would add a
        # query to every stage to answer a question nothing else asks.
        if os.getenv(FAULT_VAR, "").strip():
            # to_regclass first: selecting from a missing table raises, and in
            # PostgreSQL that aborts the caller's transaction -- so a probe for
            # something that is legitimately absent would break the very run it
            # was inspecting.
            cursor.execute("SELECT to_regclass(%s)", (SCRATCH_MARKER,))
            if cursor.fetchone()[0] is not None:
                # A savepoint, because the marker is owned by postgres and the
                # producer reads it as the app role. Without the clone's GRANT
                # this raises InsufficientPrivilege, and an unhandled error
                # here aborts the caller's whole transaction -- the producer
                # dies mid-stage instead of being permitted or refused.
                #
                # Unreadable is treated as absent, which makes the fault gate
                # refuse. Fail closed: a marker this process cannot read is not
                # an attestation it can rely on.
                cursor.execute("SAVEPOINT p0a_marker_probe")
                try:
                    cursor.execute(
                        f"SELECT database FROM {SCRATCH_MARKER} LIMIT 1")
                    row = cursor.fetchone()
                    env.scratch_marker = row[0] if row else None
                    cursor.execute("RELEASE SAVEPOINT p0a_marker_probe")
                except Exception as exc:               # noqa: BLE001
                    cursor.execute("ROLLBACK TO SAVEPOINT p0a_marker_probe")
                    log.warning("%s: %s exists but could not be read (%s); "
                                "treating as no attestation.",
                                stage, SCRATCH_MARKER,
                                type(exc).__name__)

        if owned:
            cursor.close()

    url = _redis_url()
    if url:
        parsed = urlparse(url)
        env.redis_endpoint = f"{parsed.hostname}:{parsed.port or 6379}"
        env.redis_logical_db = (parsed.path or "/0").lstrip("/") or "0"

    return env


def enforce(env: Envelope) -> None:
    """Refuse the run when an authority still points at production.

    Outside discovery this does nothing but log, so a producer carrying this
    gate behaves identically in the nightly pipeline.
    """
    for line in env.lines():
        log.info("%s", line)

    # Before the discovery short-circuit, deliberately. A production run with a
    # fault variable still set in its environment is the case that must refuse,
    # and returning early here would let it through as an ordinary production
    # run carrying a loaded gun.
    refuse_faults_outside_discovery(env)

    if not env.discovery:
        return

    if env.database != env.expected_db:
        raise EnvelopeRefused(
            f"{env.stage}: connected to '{env.database}' but this run is "
            f"confined to '{env.expected_db}'. The environment said one thing "
            f"and the connection did another, which is precisely why this is "
            f"checked against the live connection.")

    mode = os.getenv(DISCOVERY_REDIS_VAR, "").strip().lower()
    if mode == "disabled":
        return
    if not env.redis_logical_db:
        raise EnvelopeRefused(
            f"{env.stage}: REDIS_URL is unset in a discovery run, so any cache "
            f"call falls back to redis://localhost:6379/0 — production. Set "
            f"REDIS_URL to an isolated logical database or "
            f"{DISCOVERY_REDIS_VAR}=disabled.")
    if mode != "isolated":
        raise EnvelopeRefused(
            f"{env.stage}: {DISCOVERY_REDIS_VAR} is '{mode or 'unset'}'. A "
            f"discovery run must declare Redis isolated or disabled. "
            f"discovery-15 flushed production keys while its database sentinel "
            f"stayed clean, so database identity alone is no longer accepted "
            f"as the isolation proof.")


def prove(stage: str, conn=None, *, cursor=None,
          filesystem_roots: Optional[list[str]] = None) -> Envelope:
    """observe + enforce. The one call a write-producing stage makes."""
    env = observe(stage, conn, cursor=cursor, filesystem_roots=filesystem_roots)
    enforce(env)
    return env


# ── Rehearsal fault injection ────────────────────────────────────────────────
#
# Adversarial case 2 needs a failure at one exact boundary: after a complete
# provisional universe rebuild has revoked the old canonical claim, and before
# the canonical tail makes a new one. A manual kill at roughly the right moment
# is too weak -- hard to reproduce at the same boundary, impossible to
# mutation-test, and eventually somebody skips it because it was tested once.
#
# It is deliberately NOT a driver flag. `--fail-after-rebuild` would read as a
# supported production operation, sit in shell history, and be one paste away
# from the wrong terminal. An environment variable that only p0a_discovery.sh
# sets, behind the live runtime envelope, says what this actually is: a way to
# prove failure behaviour inside an isolated rehearsal.


def _fault_conditions(env: Envelope) -> list[str]:
    """Every reason this process may NOT inject a fault. Empty means it may.

    Stated as unmet conditions rather than a boolean, so a refusal can say
    which one failed. All are required together: each on its own is satisfiable
    by an environment that is not actually isolated.
    """
    unmet = []
    production = os.getenv(PRODUCTION_DB_VAR, "").strip()

    if os.getenv(DISCOVERY_MODE_VAR, "").strip().lower() != "enabled":
        unmet.append(f"{DISCOVERY_MODE_VAR} is not 'enabled'")
    if not env.expected_db:
        unmet.append(f"{EXPECTED_DB_VAR} is unset")
    elif env.database != env.expected_db:
        # The live connection, not the environment. An inherited variable is
        # intent; this is the same distinction the whole module exists for.
        unmet.append(f"this process reached '{env.database}', not "
                     f"'{env.expected_db}'")
    if not production:
        unmet.append(f"{PRODUCTION_DB_VAR} is undeclared, so 'not production' "
                     f"cannot be established")
    elif production == env.expected_db or production == env.database:
        unmet.append(f"the target database IS production ('{production}')")
    if os.getenv(DISCOVERY_REDIS_VAR, "").strip().lower() not in \
            ("isolated", "disabled"):
        unmet.append(f"{DISCOVERY_REDIS_VAR} is neither isolated nor disabled")

    # The database's own word, which no environment variable can forge. Last
    # because it is the one that still holds when every declaration above is
    # consistent and all of them are wrong.
    if env.scratch_marker is None:
        unmet.append(f"'{env.database}' carries no {SCRATCH_MARKER}, so it "
                     f"does not attest to being a rehearsal clone")
    elif env.scratch_marker != env.database:
        unmet.append(f"'{env.database}' carries a scratch marker naming "
                     f"'{env.scratch_marker}' -- this is a clone restored "
                     f"somewhere other than where it was made")
    # Production email suppression is NOT a separate condition here, because
    # it would be a duplicate: alert.py suppresses on EXPECTED_DB_VAR, which
    # the expected_db condition above already requires. A branch that cannot
    # fail independently of another one is not a safeguard, it is a second
    # copy of one -- and it reads as coverage that does not exist.
    #
    # The real risk is alert.py's condition CHANGING, which no runtime check
    # here could see. test_runtime_envelope.py asserts that coupling directly.
    return unmet


def refuse_faults_outside_discovery(env: Envelope) -> None:
    """A fault variable present without full isolation stops the process.

    Called from enforce(), so every writer carrying the gate inherits it and
    refuses BEFORE doing any work. The dangerous case is not a fault that fails
    to fire -- it is a fault variable lingering in an environment that resolves
    to production, where the safe-looking outcome is that nothing happens and
    the unsafe one is that something does.
    """
    requested = os.getenv(FAULT_VAR, "").strip()
    if not requested:
        return

    unmet = _fault_conditions(env)
    if unmet:
        raise EnvelopeRefused(
            f"{env.stage}: {FAULT_VAR}='{requested}' is set, but this process "
            f"is not in an isolated rehearsal: {'; '.join(unmet)}. Refusing "
            f"before any work. Fault injection exists to prove failure "
            f"behaviour against a scratch database and must never be reachable "
            f"from an environment that resolves to production.")

    if requested not in FAULT_POINTS:
        raise EnvelopeRefused(
            f"{env.stage}: {FAULT_VAR}='{requested}' is not a known fault "
            f"point. Known: {', '.join(sorted(FAULT_POINTS))}. An unrecognised "
            f"name is refused rather than ignored -- a typo that silently "
            f"injects nothing makes the adversarial case pass by not "
            f"happening.")


def discovery_fault(point: str, env: Envelope, log=None) -> None:
    """Fire the requested fault at this point, if this is it.

    A no-op everywhere else, including every production run: the variable is
    unset, and if it were set, enforce() would already have refused.
    """
    assert point in FAULT_POINTS, (
        f"{point!r} is not a declared fault point; add it to FAULT_POINTS so "
        f"the allowlist and the call sites cannot drift apart")

    if os.getenv(FAULT_VAR, "").strip() != point:
        return

    unmet = _fault_conditions(env)
    if unmet:                                    # pragma: no cover - enforce()
        raise EnvelopeRefused(                   # already refused this process
            f"{env.stage}: refusing to inject '{point}': {'; '.join(unmet)}")

    message = (f"INJECTED FAULT '{point}' in {env.stage} against "
               f"'{env.database}'. This is the rehearsal proving what happens "
               f"when the canonical tail does not complete.")
    if log is not None:
        log.error("%s", message)
    raise InjectedFault(message)
