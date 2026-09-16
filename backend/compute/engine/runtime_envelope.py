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


class EnvelopeRefused(RuntimeError):
    """The process reached something it was not permitted to reach."""


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
