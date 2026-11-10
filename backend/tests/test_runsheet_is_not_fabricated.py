"""The run sheet must not invent rows, and a blank must mean one thing.

The defect this guards against shipped: ten rows named `stage <`, `stage c`,
`stage o`, `stage m`, `stage p`, `stage u`, `stage t`, `stage e`, `stage d`,
`stage >`. They spell <computed>. A plan field the parser could not evaluate
fell back to that STRING, and the caller iterated it character by character.

Nothing about those rows announced they were wrong. They had sequence
numbers, cadences, statuses and on-failure text, and they sat in the middle
of a document whose whole purpose is to say what runs in what order. A
reader would have taken them for stages with unfamiliar names.

So the checks here are about FABRICATION, not correctness:

  * every stage named in the sheet is a stage the plan actually declares
  * every plan resolves, or says it did not -- never both
  * the layer vocabulary is closed, so a new token cannot slip in unnoticed
  * a blank layer means exactly one thing

None of this checks that the pipeline is right. It checks that the document
is describing the pipeline rather than describing its own parse failures.
"""

import ast
import csv
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
RUNSHEET = ROOT / "database" / "stm" / "job_execution_runsheet.csv"
RUN_PLANS = BACKEND / "compute" / "engine" / "run_plans.py"

#: Every value the layer column may hold. Closed deliberately: an unexpected
#: token is either a new layer nobody declared or a sentinel leaking into the
#: document, and both should stop the build.
ALLOWED_LAYERS = {
    "", "Bronze", "Silver", "Gold", "Universe",
    "out-of-scope", "Silver/out-of-scope",
    "(writes no table)", "(unresolved)", "UNRESOLVED",
}

EXPECT_MIN_ROWS = 60
EXPECT_MIN_LABELLED = 45


def rows() -> list[dict]:
    assert RUNSHEET.exists(), (
        f"{RUNSHEET} is missing. Run "
        f"`python backend/scripts/stm/generate_runsheet.py` from backend/.")
    with RUNSHEET.open(encoding="utf-8", newline="") as fh:
        out = list(csv.DictReader(fh))
    assert len(out) >= EXPECT_MIN_ROWS, (
        f"the run sheet has {len(out)} rows, expected at least "
        f"{EXPECT_MIN_ROWS}. A sheet that shrank is a sheet that stopped "
        f"describing part of the pipeline.")
    return out


def declared_stages() -> set[str]:
    """Stage names the plans actually declare, resolved properly.

    Resolved here INDEPENDENTLY of the generator: if both read the plans the
    same wrong way, comparing them proves nothing. This reads the plan file
    with its own evaluator and compares the result against what the document
    says.
    """
    tree = ast.parse(RUN_PLANS.read_text(encoding="utf-8"))

    env = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            try:
                env[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                pass

    def value(node):
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            pass
        if isinstance(node, ast.Name):
            return env.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = value(node.left), value(node.right)
            if isinstance(left, (tuple, list)) and isinstance(right,
                                                              (tuple, list)):
                return tuple(left) + tuple(right)
        return None

    stages = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "RunPlan"):
            continue
        for kw in node.keywords:
            if kw.arg == "stages":
                got = value(kw.value)
                assert got is not None, (
                    "a RunPlan's stages could not be resolved by this test "
                    "either. Both the generator and this guard would then be "
                    "silent about the same plan, so the test is extended "
                    "rather than the failure accepted.")
                stages.update(got)
    assert stages, "no RunPlan stages found at all"
    return stages


# ── Fabrication ─────────────────────────────────────────────────────────────

def test_every_stage_row_names_a_declared_stage():
    declared = declared_stages()
    invented = []
    for row in rows():
        name = row["job_name"]
        if not name.startswith("stage "):
            continue
        stage = name[len("stage "):].strip()
        if stage and stage not in declared:
            invented.append(stage)

    assert not invented, (
        f"the run sheet names stages the plans do not declare: "
        f"{sorted(set(invented))}. If they are single characters, a "
        f"sentinel string was iterated character by character and these rows "
        f"are fabricated.")


def test_no_row_is_a_single_character_stage():
    """The specific shape of the shipped defect, named so it cannot return.

    Subsumed by the test above, and kept separate because this one explains
    itself at a glance in a failure report.
    """
    letters = [r["job_name"] for r in rows()
               if r["job_name"].startswith("stage ")
               and len(r["job_name"][len("stage "):].strip()) == 1]
    assert not letters, (
        f"{letters} -- single-character stage names. A plan field was "
        f"iterated as a string. Read them in order: they spell the sentinel.")


def test_no_sentinel_text_reaches_the_document():
    leaked = []
    for row in rows():
        for column, cell in row.items():
            if cell and ("<computed>" in cell or "<unresolved>" in cell):
                leaked.append((row["seq"], column, cell[:40]))
    assert not leaked, (
        f"a parse sentinel is being published as content: {leaked}. A "
        f"sentinel belongs in the parser; in the document it reads as data.")


# ── Vocabulary ──────────────────────────────────────────────────────────────

def test_the_layer_vocabulary_is_closed():
    seen = {r["layer"] for r in rows()}
    unexpected = sorted(seen - ALLOWED_LAYERS)
    assert not unexpected, (
        f"unexpected layer values {unexpected}. Either a layer was added and "
        f"ALLOWED_LAYERS was not updated, or something is leaking into the "
        f"column.")


def test_a_blank_layer_means_no_script_named():
    """Blank must not also mean 'resolved to nothing' or 'parse failed'.

    One token meaning several things is how a reader concludes that twenty
    scheduled jobs touch no data, when in fact nobody looked at them.
    """
    wrong = [(r["seq"], r["job_name"][:40], r["script"][:40])
             for r in rows() if not r["layer"] and r["script"]]
    assert not wrong, (
        f"these rows are blank-layer AND name a script, so blank is carrying "
        f"two meanings: {wrong}. A named script that does not resolve should "
        f"read '(unresolved)'.")


def test_enough_of_the_sheet_is_actually_labelled():
    """Coverage, so a parse that quietly stops resolving fails.

    Every check above passes on a sheet where nothing resolves at all.
    """
    all_rows = rows()
    labelled = [r for r in all_rows
                if r["layer"] in {"Bronze", "Silver", "Gold", "Universe",
                                  "out-of-scope", "Silver/out-of-scope",
                                  "(writes no table)"}]
    assert len(labelled) >= EXPECT_MIN_LABELLED, (
        f"only {len(labelled)} of {len(all_rows)} rows carry a resolved "
        f"layer, expected at least {EXPECT_MIN_LABELLED}. The parse has "
        f"stopped resolving and every other check in this file still passes.")


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
