"""Every parameterised SQL constant must survive client-side interpolation.

psycopg2 does not send a query and its parameters separately. It interpolates
the whole query text in the client, using Python's `%` operator, and sends one
finished string. So the query is a FORMAT STRING, and that has a consequence
people forget as soon as they stop looking at the placeholders:

    a SQL comment is not inert.

A `--` comment is invisible to Postgres but fully visible to `%`. Writing

    -- 1,674 (91.1%) were wrong by more than 0.01

inside a statement that carries parameters makes `%)` a format specifier,
and the statement can never be executed again. That is not a hypothetical.
It happened on 10 Nov 2026, in the comment documenting a repair, and it
stopped the repair's first production run before a single row was written.
Every other `%` in that 2,000-line statement was correctly doubled; the one
in freshly written prose was not.

The class of defect is wider than a comment. Any literal percent -- in a
`LIKE '%foo%'` pattern, in a `to_char` format, in a number carried into a
message -- has to be doubled when the statement is parameterised. Reviewers
read the SQL for SQL and skim the prose, which is exactly backwards for this
failure mode.

So the check is the interpolation itself, performed the way the driver
performs it, over every SQL constant the module declares. Not a regex that
looks for suspicious percent signs -- a regex encodes someone's idea of
which percents are suspicious, and this one was in a comment precisely
because nobody thought comments counted.

Two populations are checked:

  1. every module-level `*_SQL` constant in the builder, on its own;
  2. the UPSERT assembled exactly as main() assembles it, which is the
     artifact that actually runs.

(2) matters separately because the assembly substitutes `{code_filter}`,
which contributes its own placeholders. A statement can be well-formed
before assembly and malformed after it.

This test reads source. It needs no database, and it would have failed on
the committed tree before the first production run of the broken statement.
"""

import ast
import string
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BUILDER = BACKEND / "scripts" / "eodhd" / "v2" / "build_screener_universe.py"

#: Modules whose SQL constants are checked. A statement carrying parameters
#: is the only kind at risk, but checking the unparameterised ones too costs
#: nothing and stops one from acquiring a parameter later without notice.
SQL_MODULES = (
    BUILDER,
    BACKEND / "scripts" / "eodhd" / "v2" / "jobs" / "daily_pipeline.py",
)

#: The builder's statement is the one this guard exists for. If the constant
#: is renamed or inlined, the guard must fail rather than quietly check
#: nothing -- a watched mechanism that is refactored away takes its coverage
#: with it.
REQUIRED_CONSTANTS = {
    BUILDER.name: {"UPSERT_SQL", "EXPECTED_CODES_SQL"},
}

#: Below this, the guard has lost its population rather than found a clean
#: tree. Chosen well under the count at the time of writing.
MIN_CONSTANTS = 3


#: Methods whose first string argument is a statement the driver will
#: interpolate. daily_pipeline keeps its SQL inline at the call site rather
#: than in named constants, so a guard that looked only at `*_SQL` names
#: would have covered none of it.
EXECUTE_METHODS = {"execute", "executemany", "_exec"}


def _inline_sql(path: Path) -> dict[str, str]:
    """String literals passed directly to an execute-like call."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in EXECUTE_METHODS
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            found[f"inline@{node.lineno}"] = node.args[0].value
    return found


def _sql_constants(path: Path) -> dict[str, str]:
    """Module-level `*_SQL` string constants, read statically.

    Parsed rather than imported: importing the builder pulls in psycopg2 and
    the compute engine, and a guard that needs the system running to check a
    syntactic property is a guard that will be skipped.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.endswith("_SQL"):
                found[target.id] = node.value.value
    return found


def _interpolate(text: str) -> None:
    """Do to `text` exactly what psycopg2 does, and let it raise.

    The placeholder count is read from the text itself, so this asks only
    "can this string be interpolated at all", never "with how many
    parameters" -- arity is a runtime property and belongs to the call site.
    """
    placeholders = text.count("%s")
    text % (("x",) * placeholders)


def _assemble_upsert() -> str:
    """The statement as main() builds it, from the real shared predicates."""
    sys.path.insert(0, str(BACKEND))
    from compute.engine.serving_population import (     # noqa: E402
        EXCLUDED_COMPANY_TYPES, current_source_predicate)

    constants = _sql_constants(BUILDER)
    base_filter = ("WHERE COALESCE(c.company_type, '') NOT IN "
                   f"({', '.join(['%s'] * len(EXCLUDED_COMPANY_TYPES))})")
    return constants["UPSERT_SQL"].format(
        code_filter=base_filter,
        current_source=current_source_predicate())


def test_every_sql_constant_can_be_interpolated():
    checked, failures = [], []
    for path in SQL_MODULES:
        assert path.exists(), f"{path} is gone; SQL_MODULES is stale"
        constants = {**_sql_constants(path), **_inline_sql(path)}

        required = REQUIRED_CONSTANTS.get(path.name, set())
        missing = sorted(required - set(constants))
        assert not missing, (
            f"{missing} are no longer module-level *_SQL constants in "
            f"{path.name}, so this guard no longer sees them. If they moved, "
            f"follow them; do not delete the expectation.")

        for name, text in constants.items():
            # Unfilled {field} braces are not this guard's business, but a
            # format field that happens to sit next to a percent would be,
            # so they are replaced with an inert token first.
            flat = text
            for _, field, _, _ in string.Formatter().parse(text):
                if field is not None:
                    flat = flat.replace("{" + field + "}", "TRUE")
            checked.append(f"{path.name}:{name}")
            try:
                _interpolate(flat)
            except Exception as exc:                     # noqa: BLE001
                failures.append(f"{path.name}:{name} -- "
                                f"{type(exc).__name__}: {exc}")

    assert len(checked) >= MIN_CONSTANTS, (
        f"only {len(checked)} SQL constants found ({checked}); expected at "
        f"least {MIN_CONSTANTS}. The guard has lost its population.")
    assert not failures, (
        "these statements cannot be sent by psycopg2:\n  "
        + "\n  ".join(failures)
        + "\n\nA literal percent in a parameterised statement must be "
          "written '%%' -- including inside a -- comment, which psycopg2 "
          "interpolates like any other text.")


def test_the_assembled_upsert_can_be_interpolated():
    """The statement that actually runs, not the constant it is built from."""
    assembled = _assemble_upsert()
    try:
        _interpolate(assembled)
    except Exception as exc:                             # noqa: BLE001
        raise AssertionError(
            f"the assembled universe upsert cannot be sent: "
            f"{type(exc).__name__}: {exc}\n"
            f"This is the exact failure the canonical run hits, before any "
            f"row is written.") from None


def test_the_assembled_upsert_carries_the_expected_parameters():
    """Arity, checked against the parameters main() actually passes.

    Interpolation succeeding is not enough: a statement with one `%s` and
    two parameters raises at execute time with a different error, and a
    statement with two `%s` and one parameter is the IndexError the broken
    run reported. Both are caught here, against the real excluded list.
    """
    sys.path.insert(0, str(BACKEND))
    from compute.engine.serving_population import (     # noqa: E402
        EXCLUDED_COMPANY_TYPES)

    assembled = _assemble_upsert()
    expected = len(EXCLUDED_COMPANY_TYPES)
    actual = assembled.count("%s")
    assert actual == expected, (
        f"the assembled upsert has {actual} placeholder(s) but main() passes "
        f"{expected} parameter(s) when --codes is not given. psycopg2 raises "
        f"IndexError when there are more placeholders than parameters.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:                         # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
