"""
Every documented config key must be declared on Settings
========================================================
pydantic-settings runs with extra="forbid". A key present in a .env file but
NOT declared on Settings raises ValidationError while Settings() is being
constructed, at import time, so uvicorn cannot load the app at all. The
failure is total, not a quiet fallback to a default.

What makes it dangerous is that it is INVISIBLE until a restart. The running
process read its configuration at startup and keeps serving on it, so adding
the key breaks nothing you can see: the site is up, /health answers 200, and
a post-deploy smoke against the live process passes. The outage is scheduled
for whenever the service next restarts.

It has happened twice:

  11 Sep 2026  SCHEDULERS_ENABLED set in .env, not declared  -> 8 min down
  25 Oct 2026  ALERT_EMAIL added for the monitor             -> caught first

Three things have to agree. This file asserts the pair that lives in the
repository; the third is checked where it actually lives:

  1. backend/.env.example     documents the key
  2. app/core/config.py       declares it as a field       <- asserted here
  3. the deployed backend/.env                             <- deploy.sh, which
     builds Settings in a fresh process BEFORE restarting anything, because
     only a fresh process distinguishes a working configuration from a
     working process.

Why the AST and not an import
-----------------------------
The first version of this file did `from app.core.config import Settings`.
That module constructs Settings at import time, so merely COLLECTING the
suite required DATABASE_URL, DATABASE_URL_SYNC and JWT_SECRET -- and where
they were absent the suite did not fail, it failed to RUN, which claims
nothing either way. A guard that cannot run is not a guard.

The property here is syntactic: is this name declared as a field? So read
the syntax. The check now needs nothing but the two files, and runs
identically in the gate, in CI and on a laptop.
"""

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = BACKEND / ".env.example"
CONFIG_PY = BACKEND / "app" / "core" / "config.py"

# KEY=value anchored at the start of a line. Comments, blanks and indented
# lines are not keys.
_KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def _documented_keys() -> set:
    return set(_KEY.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def _declared_fields() -> set:
    """Annotated assignments in `class Settings` -- i.e. pydantic fields.

    Only AnnAssign counts. A bare `X = 1` in the class body is not a field
    and would not satisfy extra="forbid" either, so matching it would make
    this guard agree with a config that still fails to start.
    """
    tree = ast.parse(CONFIG_PY.read_text(encoding="utf-8"), str(CONFIG_PY))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError(f"no `class Settings` found in {CONFIG_PY}")


def test_both_source_files_are_present():
    assert ENV_EXAMPLE.exists(), f"{ENV_EXAMPLE} is missing"
    assert CONFIG_PY.exists(), f"{CONFIG_PY} is missing"


def test_the_guard_still_has_a_population():
    """Both sides must be non-trivially sized.

    Without this, a renamed file, an emptied .env.example or a parser that
    silently stopped matching would make the coverage check below pass over
    zero keys and still report success -- a guard that lost its population
    while staying green.
    """
    documented = _documented_keys()
    declared = _declared_fields()
    assert len(documented) >= 20, (
        f"only {len(documented)} keys parsed from .env.example — the file or "
        f"the parser changed shape, and the coverage check is now blind"
    )
    assert len(declared) >= 20, (
        f"only {len(declared)} fields parsed from config.py — the AST walk "
        f"found almost nothing, so the coverage check is now blind"
    )


def test_every_documented_key_is_declared_on_settings():
    undeclared = sorted(_documented_keys() - _declared_fields())
    assert not undeclared, (
        "these keys are documented in .env.example but NOT declared in "
        "app/core/config.py. With extra=\"forbid\", any host whose .env "
        "carries one of them cannot start the API at all:\n    "
        + "\n    ".join(undeclared)
    )


@pytest.mark.parametrize("key", ["RESEND_API_KEY", "EMAIL_FROM", "ALERT_EMAIL"])
def test_the_monitor_s_keys_are_declared(key):
    """Named individually so that removing one from .env.example cannot
    quietly retire the case along with it.

    The monitor reads these from the environment and never imports Settings
    -- deliberately, so it does not share fate with the app it watches. But
    they live in the same .env, so the APP still has to tolerate them.
    ALERT_EMAIL is the one that was latent on 25 Oct 2026.
    """
    assert key in _declared_fields(), (
        f"{key} is set in the deployed backend/.env for the primary-feature "
        f"monitor. Undeclared, it stops the API starting."
    )
