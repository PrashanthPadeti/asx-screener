"""The linter's verdict must cover every directory of Python it is read as.

On 11 Nov 2026 `scripts/eodhd/v2/build_screener_universe.py` reached
production referring to a local that a refactor two commits earlier had
deleted. The first canonical run died at the universe stage:

    NameError: name 'EXCLUDED_TYPES' is not defined

`ruff check --select F821` names all three call sites, at their exact lines,
on the deployed file. The rule was selected. The linter was pinned. The
config was declared, deliberately, with a written argument for every rule in
it. None of that mattered, because CI ran

    ruff check app/ compute/

and the defect was in `scripts/`, which is where every pipeline producer
lives. Four directories under backend/ hold Python; two were linted. The
verdict "All checks passed" was true of the part that was measured and
carried nothing about the part that was not.

That is the standing rule about scoped verdicts, met in a new place. A check
whose population is a path list drifts the moment someone adds a directory,
and nothing about a passing lint step tells a reader which tree it walked.

So this test asserts the population, not the rules:

  1. every directory under backend/ containing Python is in the command;
  2. so is every loose module at the root;
  3. the command names a ruff that is PINNED, because an unpinned linter is
     a gate owned by PyPI -- that already turned main red once, around
     21 Oct 2026, with no change to this repository;
  4. F821 -- the rule that would have caught this -- is selected, and is not
     suspended for any path in per-file-ignores.

(4) is the load-bearing one. Adding `scripts/` to the path list while
suspending F821 inside it would leave this file's other assertions passing
and the system exactly as able to ship the next NameError. Suspending a rule
is allowed and sometimes necessary -- scripts/ entered with 70 pre-existing
findings and four rules suspended by count -- but not this rule, and never
silently.

Reads files. Needs no database, no ruff installed, and no network.
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
CI = REPO / ".github" / "workflows" / "ci.yml"
RUFF_TOML = BACKEND / "ruff.toml"

#: Directories under backend/ that may hold Python without being linted.
#: Empty on purpose. A new entry here is a deliberate, reviewable decision to
#: stop measuring something; the default is that everything is measured.
EXEMPT_DIRS: set[str] = set()

#: Not source trees.
SKIP_DIRS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "node_modules", ".venv", "venv", "asx-venv", ".git",
}

#: The rule that found this defect. Not suspendable anywhere.
#: F821 is pyflakes' undefined-name check: a name that cannot resolve at the
#: point it is read. Every instance is a crash waiting for its line to run,
#: which for a nightly producer means waiting for the next night.
UNSUSPENDABLE = "F821"


def _ruff_command() -> str:
    """The `ruff check ...` line from the lint job."""
    text = CI.read_text(encoding="utf-8")
    m = re.search(r"^\s*run:\s*cd backend && ruff check (.+)$", text, re.M)
    assert m, (
        f"no `cd backend && ruff check ...` run line in {CI.name}. This test "
        f"reads the real CI command rather than restating it; if the lint "
        f"step moved or changed shape, follow it here. Deleting this test "
        f"because it no longer matches is how the population was lost the "
        f"first time.")
    return m.group(1).strip()


def _linted_paths() -> set[str]:
    return {p.strip().rstrip("/") for p in _ruff_command().split() if p.strip()}


def _python_bearing_dirs() -> set[str]:
    """Top-level directories under backend/ that contain any .py file."""
    out = set()
    for child in BACKEND.iterdir():
        if not child.is_dir() or child.name in SKIP_DIRS:
            continue
        for path in child.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            out.add(child.name)
            break
    return out


def _root_modules() -> set[str]:
    return {p.name for p in BACKEND.glob("*.py")}


def _ruff_section(name: str) -> str:
    """The body of a `[lint.<name>]`-style section, or ''."""
    text = RUFF_TOML.read_text(encoding="utf-8")
    m = re.search(rf"^\[{re.escape(name)}\]\s*$(.*?)(?=^\[|\Z)",
                  text, re.M | re.S)
    return m.group(1) if m else ""


def test_every_python_directory_is_linted():
    linted = _linted_paths()
    dirs = _python_bearing_dirs()
    missing = sorted(dirs - linted - EXEMPT_DIRS)

    assert dirs, (
        "no Python-bearing directories were found under backend/. This test "
        "has lost its population and would pass against an empty tree.")
    assert not missing, (
        f"{missing} contain Python and are not in the CI lint command "
        f"({sorted(linted)}).\n\n"
        f"A lint step that walks part of the tree reports on part of the "
        f"tree. `ruff check app/ compute/` passed on 10 Nov 2026 while "
        f"scripts/eodhd/v2/build_screener_universe.py held three references "
        f"to an undefined name, and the universe build died on the first of "
        f"them in production.\n\n"
        f"Add the directory here. If it genuinely must not be linted, put it "
        f"in EXEMPT_DIRS with a reason -- so that it is a decision somebody "
        f"made, not a gap nobody saw.")


def test_loose_root_modules_are_linted():
    """A module at backend/ root is in no directory and easy to miss."""
    linted = _linted_paths()
    missing = sorted(m for m in _root_modules() if m not in linted)
    assert not missing, (
        f"{missing} sit at backend/ root and are covered by no directory in "
        f"the lint command. worker.py is the process-independence worker: it "
        f"runs the canonical pipeline on its own, and nothing else would "
        f"lint it.")


def test_the_linter_is_pinned():
    text = CI.read_text(encoding="utf-8")
    m = re.search(r"pip install ruff==(\S+)", text)
    assert m, (
        "ruff is not installed at a pinned version in the lint job. "
        "Unpinned, which rules apply is decided by whatever is newest on "
        "PyPI, and `main` can turn red with no change to this repository -- "
        "which happened around 21 Oct 2026. Pin it, and read the new "
        "findings when you bump it.")


def test_the_rule_that_caught_this_is_selected():
    select = _ruff_section("lint")
    m = re.search(r"^select\s*=\s*\[(.*?)\]", select, re.M | re.S)
    assert m, f"no `select` list in {RUFF_TOML.name}'s [lint] section."
    families = {s.strip().strip('"\'') for s in m.group(1).split(",")
                if s.strip()}
    # F821 is in the F family; either the family or the rule itself counts.
    covered = UNSUSPENDABLE in families or any(
        UNSUSPENDABLE.startswith(f) for f in families if f)
    assert covered, (
        f"{UNSUSPENDABLE} is not selected (select = {sorted(families)}). It "
        f"is the undefined-name check, and it is the rule that named the "
        f"defect which stopped the universe build on 11 Nov 2026.")


def test_the_rule_that_caught_this_is_suspended_nowhere():
    """The repair is the scope, not an exemption inside the new scope.

    This is the mutant worth worrying about: add scripts/ to the path list,
    then add F821 to its ignore list. Every other test in this file would
    still pass, the lint step would still be green, and the next NameError
    in a producer would ship exactly as this one did.
    """
    section = _ruff_section("lint.per-file-ignores")
    offenders = [line.strip() for line in section.splitlines()
                 if UNSUSPENDABLE in line and not line.strip().startswith("#")]
    assert not offenders, (
        f"{UNSUSPENDABLE} is suspended for some path:\n  "
        + "\n  ".join(offenders)
        + f"\n\nSuspending a rule per-path is legitimate -- scripts/ entered "
          f"the lint population with four rules suspended by count, which is "
          f"how it entered at all. {UNSUSPENDABLE} is not one of them. Every "
          f"finding it reports is a name that cannot resolve when its line "
          f"runs, and in a nightly producer that line runs at 03:44.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
            print(f"  FAIL  {fn.__name__}")
        except Exception as exc:                         # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {fn.__name__}")
    print()
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
