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


def test_the_smoke_script_resolves_config_itself():
    """deploy.sh does not export backend/.env to the subprocess.

    The lookup must consult the environment AND the .env file, or a value
    placed where the operator was told to put it is invisible.

    Checked on _env_value, which owns the resolution. The first version
    asserted on _smoke_token and broke the moment that delegated -- a guard
    pointed at a function that no longer does the work reports on nothing.
    """
    tree = ast.parse(SMOKE.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_env_value"),
              None)
    assert fn is not None, (
        "the smoke script has no _env_value(); nothing resolves config at "
        "its own execution boundary")
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
        f"_env_value never names .env in its code (only string literals "
        f"found: {sorted(literals)}), so a value placed there is never found")


def test_smoke_ai_is_declared_and_defaults_off():
    """The opt-in flag is a .env key like any other: undeclared, it stops
    every process from starting."""
    fields = _settings_fields()
    assert "SMOKE_AI" in fields, (
        "SMOKE_AI is not declared in Settings; setting it in .env would "
        "raise ValidationError at import time")
    assert ast.literal_eval(fields["SMOKE_AI"].value) is False, (
        "SMOKE_AI must default off — no deploy should spend money on a "
        "third-party API without being asked")


def test_the_token_is_minted_not_stored():
    """Access tokens live 15 minutes. A token pasted into .env is rejected
    the same afternoon and every deploy after it, and the quickest route to a
    green deploy is to delete it — restoring the blindness."""
    src = SMOKE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_smoke_token"),
              None)
    assert fn is not None, "_smoke_token is gone"
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)) else fn.body
    # The LAST statement must be the mint, not merely a mint somewhere in
    # the body. Asserting "encode is called" passed a mutation that inserted
    # `return None` above it: the call was still present and had become dead
    # code. A guard that proves intent is not a guard that proves behaviour.
    final = body[-1] if body else None
    assert isinstance(final, ast.Return) and isinstance(final.value, ast.Call)         and isinstance(final.value.func, ast.Attribute)         and final.value.func.attr == "encode", (
        "_smoke_token does not end by returning a freshly encoded JWT, so "
        "it can only use a stored token — which expires 15 minutes after it "
        "is created, and then every deploy reports a rejected token")


def test_the_minted_token_is_real():
    """Behavioural, because the structural version could not be.

    A check for "encode is called in the body" passed a mutation inserting
    `return None` above it -- the call was present and dead. A check for "the
    last statement returns an encode" passed the same mutation, because the
    early return leaves the last statement untouched. Reachability is not
    something to approximate with an AST walk, so this calls the function and
    looks at what comes back.

    Skipped where no JWT library exists (this is a dev box); it runs in the
    gate and on the server, which is where the token is actually minted.
    """
    import importlib.util
    try:
        import jwt as pyjwt                                    # noqa: F401
    except ImportError:
        try:
            from jose import jwt as pyjwt                      # noqa: F401
        except ImportError:
            raise Skipped("a JWT library (pyjwt or python-jose)")

    spec = importlib.util.spec_from_file_location("smoke_mod", SMOKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    import os
    before = {k: os.environ.get(k) for k in ("SMOKE_TOKEN", "JWT_SECRET")}
    try:
        os.environ["SMOKE_TOKEN"] = ""
        os.environ["JWT_SECRET"] = "test-secret-not-the-real-one"
        token = mod._smoke_token()
        assert token, "no token was minted from a readable JWT_SECRET"
        assert token.count(".") == 2, f"not a JWT: {token[:40]}"
        claims = pyjwt.decode(token, "test-secret-not-the-real-one",
                              algorithms=["HS256"])
        assert claims["plan"] == "premium", (
            f"the minted token is not Pro/Premium: plan={claims.get('plan')}")
        assert claims["type"] == "access"
        assert claims["email"].endswith(".invalid"), (
            "the smoke identity must be unresolvable, not a real address")
    finally:
        for k, v in before.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_ai_query_is_opt_in_and_query_mode_is_not():
    """The asymmetry is the point: one is free, the other spends money."""
    src = SMOKE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    ai = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "smoke_ai_query")
    qm = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "smoke_query_mode")
    ai_literals = {n.value for n in ast.walk(ai)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    qm_literals = {n.value for n in ast.walk(qm)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "SMOKE_AI" in ai_literals, (
        "AI Query is not gated on SMOKE_AI; every deploy would call the "
        "Anthropic API")
    assert "SMOKE_AI" not in qm_literals, (
        "Query Mode is gated on the AI opt-in, so the free check nobody "
        "objects to would be skipped along with the paid one")


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
    assert "NOT verified by this run" in src, (
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
