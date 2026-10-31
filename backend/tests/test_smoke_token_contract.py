"""
The deploy's own verification of its two Premium features
=========================================================
Query Mode and AI Query reported SKIPPED in every post-deploy smoke through
six consecutive releases on 29-30 Oct 2026 -- including v11.2.67 and v11.2.68,
which WERE Query Mode. Every verification of those features was a person
clicking a page and pasting a screenshot.

The smoke script was already written and already correct. One environment
variable was missing, and three separate things had to be true before it could
be supplied:

1. SMOKE_TOKEN must be DECLARED in Settings. pydantic-settings uses
   extra="forbid", so putting an undeclared key in backend/.env raises
   ValidationError while Settings() is constructed, at import time -- no
   process starts. SCHEDULERS_ENABLED did exactly that on 11 Sep 2026: eight
   minutes of downtime. The declaration must ship BEFORE the key is set,
   which is why this is a release and not an ops task.

2. The smoke script must find it. deploy.sh runs the script as a subprocess
   and does not export backend/.env into its environment, so a token placed
   there would have been invisible and the modes would have kept reporting
   SKIPPED -- the same blindness, now with a token sitting in a file that
   nobody could see was unused.

3. A REJECTED token must not look like a broken feature. A JWT expires.
   Reported as a bare "HTTP 401" it reads as the product being down, and the
   fastest way to make the deploy green again is to unset SMOKE_TOKEN --
   silently restoring the blindness it was added to remove.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_smoke_token_contract.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CONFIG  = BACKEND / "app/core/config.py"
SMOKE   = BACKEND / "scripts/smoke_primary_features.py"
DEPLOY  = BACKEND.parent / "deploy.sh"

sys.path.insert(0, str(BACKEND))


class Skipped(Exception):
    """Needs a runtime dependency this environment does not have."""


def _settings_fields() -> dict:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    cls = next((n for n in ast.walk(tree)
                if isinstance(n, ast.ClassDef) and n.name == "Settings"), None)
    assert cls is not None, "Settings is gone from config.py"
    return {n.target.id: n for n in cls.body
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}


def test_smoke_token_is_declared_in_settings():
    """Without this, setting the key is an outage on the next restart."""
    assert "SMOKE_TOKEN" in _settings_fields(), (
        "SMOKE_TOKEN is not declared in Settings. extra='forbid' means "
        "putting it in backend/.env raises ValidationError at import time and "
        "no process can start — the SCHEDULERS_ENABLED failure of 11 Sep "
        "2026, repeated.")


def test_the_declaration_defaults_to_empty():
    """A host without a token must skip loudly, not fail to boot."""
    node = _settings_fields()["SMOKE_TOKEN"]
    assert node.value is not None, "SMOKE_TOKEN has no default, so a host "\
                                   "without one cannot construct Settings"
    assert ast.literal_eval(node.value) == "", (
        "SMOKE_TOKEN must default to empty; any other default would be a "
        "credential in source code")


def test_settings_constructs_without_a_token():
    """The property the declaration exists for, exercised rather than read."""
    try:
        from app.core.config import Settings
    except ImportError as e:
        raise Skipped(f"config's dependencies ({e.name})")
    assert Settings().SMOKE_TOKEN == "", (
        "Settings() does not build with SMOKE_TOKEN unset")


def test_the_smoke_script_resolves_the_token_itself():
    """deploy.sh does not export backend/.env to the subprocess.

    Structural: the script must read the .env file, not only os.environ, or a
    token placed where the operator was told to put it is invisible.
    """
    src = SMOKE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_smoke_token"),
              None)
    assert fn is not None, (
        "the smoke script has no _smoke_token(); it reads os.environ only, "
        "and deploy.sh runs it as a subprocess without exporting .env")
    assert "environ" in ast.dump(fn), "the environment must still win"

    # String CONSTANTS in the body, with the docstring removed. ast.unparse()
    # includes the docstring, so asserting '".env" in ast.unparse(fn)' passed
    # a mutation that pointed the lookup at a different filename -- the
    # docstring explaining the defect still said ".env". An AST check that is
    # stringified is a textual check wearing a costume.
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)
                           and isinstance(fn.body[0].value.value, str)) else fn.body
    literals = {n.value for stmt in body for n in ast.walk(stmt)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert ".env" in literals, (
        f"_smoke_token never names .env in its code (only string literals "
        f"found: {sorted(literals)}), so a token placed there is never found")


def test_a_rejected_token_is_distinguished_from_a_broken_feature():
    """401 must say so. Otherwise the cheapest way to a green deploy is to
    unset the token, which restores the blindness."""
    src = SMOKE.read_text(encoding="utf-8")
    assert "_rejected" in src, (
        "nothing distinguishes a rejected token from a failing feature")
    assert "401" in src and "403" in src, (
        "the smoke does not branch on the auth status codes")
    assert "do not unset it" in src, (
        "the message does not warn against the fix that recreates the "
        "original defect")


def test_both_authenticated_modes_are_still_covered():
    """Population control: the token exists to exercise exactly these two."""
    src = SMOKE.read_text(encoding="utf-8")
    for mode in ("Query Mode", "AI Query"):
        assert f'"{mode}"' in src, f"{mode} is no longer smoke-tested"
    assert "NOT VERIFIED" in src, (
        "the skip path no longer announces what went unverified; a silent "
        "skip is indistinguishable from a pass")


def test_the_deploy_still_builds_settings_before_restarting():
    """The guard that turns a bad key into a refused deploy instead of an
    outage. Setting SMOKE_TOKEN is the next thing that will exercise it."""
    src = DEPLOY.read_text(encoding="utf-8")
    assert "check_configuration" in src
    assert "from app.core.config import Settings; Settings()" in src, (
        "deploy.sh no longer constructs Settings in a fresh process, so an "
        "undeclared .env key would land on the next restart instead of here")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures, skipped = [], []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Skipped as e:
            skipped.append(name)
            print(f"  SKIP  {name}  - needs {e}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    passed = len(tests) - len(failures) - len(skipped)
    print(f"\n{passed}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
