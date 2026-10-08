"""Compute engines.

This package body exists to install log redaction before any engine module
runs. Every engine calls `logging.basicConfig` at import, and `basicConfig` is
a no-op once a root handler exists -- so configuring the sink here, first,
means those later calls cannot replace the handler the redaction filter is
attached to.

Without this, httpx's INFO request logging writes `api_token=<key>` into
logs/backend.log on every EODHD call. See app/core/log_redaction.py.
"""

import logging
import sys
from pathlib import Path

# Put backend/ on the path before importing `app`. Only 18 of the 54 engine
# modules import `app.*` at all, so without this line the import below would
# make `app` a hard requirement for the other 36 -- fine under the service's
# WorkingDirectory, but a job invoked from any other cwd would die on import,
# and all of them would, at once. parents[2] is backend/, the same anchor
# asx_indices already uses for load_dotenv.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.log_redaction import install_secret_redaction   # noqa: E402

install_secret_redaction(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
