"""
Every `from app.…` import names a module that exists
====================================================
`python -m py_compile` proves a file PARSES. It says nothing about whether
the names it imports exist, so a wrong module path is syntactically perfect
and fatal at startup: uvicorn cannot load the app at all.

That has now happened twice in this codebase, and the second time was while
adding a page about the first:

  11 Sep 2026  an undeclared .env key      -> API down 8 minutes
  26 Oct 2026  `from app.core.database import get_db`, which does not exist
               (`app.db.session` does)     -> caught by the gate

The second was caught only because the primary-feature contract tests import
the application, so a bad import surfaced as eleven unrelated-looking
failures with `ModuleNotFoundError` buried in them. This check costs
milliseconds and names the file and the line.

Static, not an import. Actually importing every module would execute them --
and importing app.main has twice started real scheduled jobs on the
production host. An instrument must not join the system it observes, so this
reads the AST and resolves paths on disk.
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

ROOTS = ("app", "compute")


def _module_exists(dotted: str) -> bool:
    """True if `dotted` resolves to a module file or a package."""
    base = BACKEND / Path(dotted.replace(".", "/"))
    return base.with_suffix(".py").exists() or (base / "__init__.py").exists()


def _scan() -> tuple[list[str], int]:
    """(broken, files_scanned)."""
    broken: list[str] = []
    scanned = 0
    for root in ROOTS:
        for path in sorted((BACKEND / root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            scanned += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            except SyntaxError as exc:
                broken.append(f"{path.relative_to(BACKEND)} does not parse: {exc}")
                continue
            for node in ast.walk(tree):
                # Only absolute imports rooted at our own packages. Relative
                # imports and third-party packages are not ours to resolve.
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.level or not node.module:
                    continue
                if node.module.split(".")[0] not in ROOTS:
                    continue
                if _module_exists(node.module):
                    continue
                # `from app.core.config import settings` -- the module is the
                # thing being resolved here, not the names inside it.
                broken.append(
                    f"{path.relative_to(BACKEND)}:{node.lineno} imports "
                    f"'{node.module}', which does not exist")
    return broken, scanned


def test_the_scan_has_a_population():
    """Without this, a renamed directory would make the check below pass
    over zero files while still reporting success."""
    _, scanned = _scan()
    assert scanned >= 50, (
        f"only {scanned} python files scanned under {ROOTS}; the scan has "
        f"lost its population and proves nothing")


def test_every_internal_import_resolves():
    broken, _ = _scan()
    assert not broken, (
        "these imports name modules that do not exist. Each one stops the "
        "application starting, and py_compile reports the file as fine:\n    "
        + "\n    ".join(broken))


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
