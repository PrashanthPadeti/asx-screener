"""The narrative documents must still agree with what they describe.

Deliverables #2 and #3 are prose. Prose cannot be regenerated and compared
the way the sidecars can, and it carries the numbers a reader will quote:
"242 modules", "67 rows", "641 of 2,566". Those are the parts that rot.

A stale number in a document like this is worse than a missing one. The
document reads as reviewed, and a reader who checks a figure against it and
finds agreement stops checking. So every COUNT the narratives assert is
listed here with the artifact it came from, and the test fails when the two
diverge -- naming the figure and both values, so the fix is to edit one
sentence rather than to re-audit the file.

What this does NOT check is whether the prose is true. Nothing can. It
checks that the arithmetic in it still describes the system, which is the
part that changes without anyone touching the document.
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
STM = ROOT / "database" / "stm"

DOC2 = STM / "02_data_processing_and_loading.md"
DOC3 = STM / "03_job_execution_runsheet.md"
RUNSHEET = STM / "job_execution_runsheet.csv"
LINEAGE = STM / "lineage.json"
SNAP_UNIVERSE = STM / "snap_universe.json"
JOINS = STM / "evidence" / "universe_joins.json"


def _text(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _rows() -> list[dict]:
    with RUNSHEET.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _lineage() -> dict:
    return json.loads(_text(LINEAGE))


def _layer_counts() -> Counter:
    counts = Counter()
    for info in _lineage()["by_table"].values():
        counts[info.get("layer") or "(none)"] += 1
    return counts


def _assert_states(doc: Path, number: int, context: str, what: str,
                   label: str):
    """The document must state `number` NEXT TO `label`.

    An earlier version searched the whole document for the number and
    nothing else. That is a proxy, and it failed exactly as a proxy does:
    when the Universe table count moved from 5 to 4 and out-of-scope from 19
    to 20, both checks still passed, because "4" appears in "L4" and "20" in
    "Gold 20 tables" elsewhere on the page. Two stale figures sat in a
    published document under a green test.

    The mutation run that was supposed to catch this did not, because the
    mutants used values (64, 11) that happened to appear nowhere else. A
    mutant chosen for convenience tests the convenience.

    So the number and its label must appear within the same line, in either
    order, separated by at most a short span of text.
    """
    text = _text(doc)
    lab = re.escape(label)
    num = (rf"(?<![\d,.])(?:{re.escape(str(number))}"
           rf"|{re.escape(f'{number:,}')})(?![\d,.])")
    near = re.compile(rf"(?:{lab}[^\n]{{0,70}}?{num}|{num}[^\n]{{0,70}}?{lab})",
                      re.IGNORECASE)
    assert near.search(text), (
        f"{doc.name} does not state {what} as {number:,} anywhere near the "
        f"words “{label}”. The artifact now says {number:,}. "
        f"Update the sentence about {context}, and keep the figure beside "
        f"its label so this check stays a check.")


# ── Deliverable #3 against the run sheet ────────────────────────────────────

def test_doc3_row_count():
    _assert_states(DOC3, len(_rows()), "the CSV companion",
                   "the run sheet row count", "row")


def test_doc3_cadence_counts():
    counts = Counter(r["cadence"] for r in _rows())
    for cadence in ("daily", "weekly", "monthly", "scheduler",
                    "plan:DAILY_CANONICAL",
                    "plan:FULL_FUNDAMENTALS_CANONICAL"):
        _assert_states(DOC3, counts[cadence], f"the {cadence} cadence",
                       f"the {cadence} row count", cadence)


def test_doc3_scheduler_resolution_split():
    sched = [r for r in _rows() if r["cadence"] == "scheduler"]
    unresolved = [r for r in sched if r["layer"] == "(unresolved)"]
    resolved = len(sched) - len(unresolved)
    _assert_states(DOC3, resolved, "scheduler jobs that resolve",
                   "the resolved scheduler count", "resolve")
    _assert_states(DOC3, len(unresolved), "scheduler jobs that do not resolve",
                   "the unresolved scheduler count", "do not resolve")


def test_doc3_names_every_unresolved_scheduler_job():
    """Naming them is the point -- a count alone cannot be acted on."""
    text = _text(DOC3)
    missing = [r["job_name"] for r in _rows()
               if r["cadence"] == "scheduler" and r["layer"] == "(unresolved)"
               and r["job_name"] not in text]
    assert not missing, (
        f"{missing} are scheduler jobs whose data effects are unknown and "
        f"{DOC3.name} does not name them. An unnamed unknown cannot be "
        f"closed by whoever reads this.")


# ── Deliverable #2 against the lineage and the snapshot ─────────────────────

def test_doc2_module_counts():
    lineage = _lineage()
    modules = lineage.get("by_module", {})
    _assert_states(DOC2, len(modules), "the lineage scan",
                   "the module count", "modules scanned")


def test_doc2_layer_table_counts():
    """Layer counts must be stated as "<layer> ... N tables", on one line.

    The looser "number near label" rule was still a proxy here: when Universe
    went from 5 tables to 4, the check passed on a coincidental `| 4 | ...
    `universe`` in an unrelated findings table. A count of TABLES has to be
    stated as a count of tables.

    out-of-scope is included because it was previously not checked at all,
    and its figure went stale (19 -> 20) with every test green.
    """
    counts = _layer_counts()
    text = _text(DOC2)
    wrong = []
    for layer in ("Bronze", "Silver", "Gold", "Universe", "out-of-scope",
                  "UNCLASSIFIED"):
        n = counts[layer]
        pattern = re.compile(
            rf"{re.escape(layer)}[^\n]{{0,40}}?(?<![\d,.]){n}(?![\d,.])"
            rf"\s*tables?\b", re.IGNORECASE)
        if not pattern.search(text):
            wrong.append(f"{layer}: artifact says {n}")
    assert not wrong, (
        f"{DOC2.name} does not state these layer sizes as "
        f"“<layer> … N tables” on one line: {wrong}. Write the "
        f"count as a count of tables beside its layer name, or this check "
        f"matches any stray digit on the page.")


def test_doc2_unclassified_tables_are_named():
    lineage = _lineage()
    text = _text(DOC2)
    unclassified = [t for t, i in lineage["by_table"].items()
                    if i.get("layer") == "UNCLASSIFIED"]
    missing = [t for t in unclassified if t not in text]
    assert not missing, (
        f"{missing} are UNCLASSIFIED and {DOC2.name} does not name them. A "
        f"table nobody placed must be visible, or it will be placed by "
        f"accident.")


def test_doc2_universe_shape():
    snap = json.loads(_text(SNAP_UNIVERSE))
    columns = snap["meta"]["counts"]["columns"]
    rows = snap["tables"][0][3]
    _assert_states(DOC2, columns, "screener.universe",
                   "the universe column count", "columns")
    _assert_states(DOC2, rows, "screener.universe",
                   "the universe row count", "rows")


def test_doc2_join_cardinality_numbers():
    sources = json.loads(_text(JOINS))["sources"]
    laterals = [s for s in sources if s["kind"] == "lateral"]
    limited = sum(1 for s in laterals if s["limit_1"])
    aggregated = sum(1 for s in laterals if s.get("aggregate_no_group"))
    _assert_states(DOC2, len(sources), "the join cardinality table",
                   "the source count", "sources")
    _assert_states(DOC2, limited, "the join cardinality table",
                   "the LIMIT 1 lateral count", "LIMIT 1")
    _assert_states(DOC2, aggregated, "the join cardinality table",
                   "the aggregating lateral count", "aggregate")


# ── Both documents exist and are not stubs ──────────────────────────────────

def test_both_narratives_are_substantial():
    """A truncated document passes every numeric check above.

    Each of those tests searches for a number; a file containing only those
    numbers would satisfy all of them. This is the floor.
    """
    for doc in (DOC2, DOC3):
        text = _text(doc)
        assert len(text) > 4000, (
            f"{doc.name} is {len(text)} characters. It was truncated or "
            f"replaced by a stub, and every numeric check above would still "
            f"pass on a file that only held the numbers.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
