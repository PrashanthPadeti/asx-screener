"""
Database configuration
======================
One place that answers "what is the database URL", so the credential lives in
the environment and nowhere else.

Every consumer used to carry its own copy:

    os.getenv("DATABASE_URL_SYNC", "postgresql://asx_user:<password>@...")

which put the production password in 54 files in this repository, and this
repository is public. The fallback is what made that possible — it let the
credential be source code rather than configuration, and it meant a missing
environment variable produced a working connection instead of an error, so
nothing ever forced the config to be correct.

There is deliberately no fallback here. A missing DATABASE_URL_SYNC raises,
loudly, at the point of use.

This module covers configuration only, not connections. Callers use psycopg2,
SQLAlchemy sync engines and asyncpg with different lifecycles; funnelling them
through one engine would turn a credential fix into an architectural change.
"""
import os

_ENV_VAR = "DATABASE_URL_SYNC"


def get_database_url_sync() -> str:
    """
    The configured synchronous PostgreSQL URL.

    Raises RuntimeError when unset. Scripts that call this should already have
    run load_dotenv(), which reads the .env beside the working directory.
    """
    url = os.getenv(_ENV_VAR)
    if not url:
        raise RuntimeError(
            f"{_ENV_VAR} is required but is not configured. "
            "Set it in the environment or in the .env file for this project. "
            "There is no built-in default: the credential must not live in "
            "source code."
        )
    return url
