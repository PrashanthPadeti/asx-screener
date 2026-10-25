"""
Configuration must build — and every documented key must be declared
====================================================================
pydantic-settings runs with extra="forbid". A key present in a .env file but
NOT declared on Settings raises ValidationError while Settings() is being
constructed, at import time, so uvicorn cannot load the app at all. The
failure is total, not a quiet fallback to a default.

What makes it dangerous is that it is INVISIBLE until a restart. The running
process read its configuration at startup and keeps serving on it, so adding
the key breaks nothing you can see: the site is up, /health answers 200, a
post-deploy smoke against the live process passes. The outage is scheduled
for whenever the service next restarts.

It has happened twice:

  11 Sep 2026  SCHEDULERS_ENABLED set in .env, not declared  -> 8 min down
  25 Oct 2026  ALERT_EMAIL added for the monitor             -> caught here

Three things now have to agree, and this asserts the pair that lives in the
repository:

  1. backend/.env.example     documents the key
  2. app/core/config.py       declares it as a field       <- asserted here
  3. the deployed backend/.env                             <- deploy.sh,
     which builds Settings in a fresh process BEFORE restarting anything,
     because only a fresh process distinguishes a working configuration from
     a working process.
"""

import re
from pathlib import Path

import pytest

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

# KEY=value at the start of a line. Comments and blanks are skipped by the
# anchor; an indented line is not a key.
_KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def _documented_keys() -> set[str]:
    return set(_KEY.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def test_the_example_env_file_is_present_and_not_empty():
    """The population for the test below comes from this file.

    Without this, a renamed or emptied .env.example would make the coverage
    check below pass over zero keys while still reporting success -- a guard
    that lost its population.
    """
    assert ENV_EXAMPLE.exists(), f"{ENV_EXAMPLE} is missing"
    keys = _documented_keys()
    assert len(keys) >= 20, (
        f"only {len(keys)} keys parsed from .env.example — the parser or the "
        f"file changed shape, and the coverage check below is now blind"
    )


def test_every_documented_key_is_declared_on_settings():
    declared = set(Settings.model_fields)
    undeclared = sorted(_documented_keys() - declared)
    assert not undeclared, (
        "these keys are documented in .env.example but NOT declared in "
        "app/core/config.py. With extra=\"forbid\", any host whose .env "
        "carries one of them cannot start the API at all:\n    "
        + "\n    ".join(undeclared)
    )


def test_settings_builds_from_the_declared_defaults():
    """A fresh construction, which is what a restart does.

    _env_file=None so the developer's own .env cannot make this pass or fail;
    the question here is whether the MODEL is coherent.
    """
    s = Settings(_env_file=None)
    assert s.APP_VERSION, "APP_VERSION must be set"


def test_alert_email_is_declared():
    """The specific key that was latent on 25 Oct 2026.

    Named rather than left to the coverage test above so that deleting it
    from .env.example cannot quietly retire the case.
    """
    assert "ALERT_EMAIL" in Settings.model_fields, (
        "ALERT_EMAIL is set in the deployed backend/.env for the "
        "primary-feature monitor. Undeclared, it stops the API starting."
    )


@pytest.mark.parametrize("key", ["RESEND_API_KEY", "EMAIL_FROM", "ALERT_EMAIL"])
def test_the_monitor_s_keys_are_all_declared(key):
    """The monitor reads these from the environment and never imports
    Settings -- deliberately, so it does not share fate with the app it
    watches. But they live in the same .env, so the APP still has to tolerate
    them."""
    assert key in Settings.model_fields
