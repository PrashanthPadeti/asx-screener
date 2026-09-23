"""
Does Gate B fail when it should?
================================
A gate's green result means nothing until each assertion has been shown
capable of going red. This codebase has produced several guards that examined
nothing and reported PASS — an ordering guard that scanned for statements that
were not there, a fault-injection guard that matched the module's own
docstring — and each one was believed until it was mutated.

So: take the real gate, break ONE thing, run it as a subprocess, and require a
non-zero exit. Four mutations, chosen to sit on the four load-bearing claims:

    resolver expectation      the run the resolver serves is the run we anchored
    finalisation requirement  required stages must be SUCCESS
    run anchoring             assertions are about THIS run, not the newest one
    governed projection       an attributed row's governed value is served

Every mutation is applied by string substitution and the harness refuses to
run one that did not match — an inert mutation reports PASS for the same
reason an inert guard does, and would be the most expensive kind of green
result here.

    cd /opt/asx-screener/backend && ../asx-venv/bin/python scripts/gate_b_mutations.py --run-id 5
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent / "gate_b.py"

#: (name, what the mutation asserts instead, exact source fragment, replacement)
#:
#: Each mutation INVERTS an expectation so that it contradicts reality, and the
#: assertion must then fire against the live database.
#:
#: The first draft did the opposite — it made each assertion vacuously true
#: (`x in y` became `x not in y or True`) — and four of the five "survived",
#: correctly. Disabling an assertion cannot make a healthy gate fail; it just
#: removes a check from a run that was going to pass anyway. That design
#: proved nothing, and had the gate been entirely inert it would have produced
#: the same output.
#:
#: The distinction matters because the usual form of mutation testing — break
#: the SYSTEM, see whether the test notices — is unavailable here: the gate is
#: read-only by construction, so there is no way to corrupt the publication it
#: judges. Inverting the expectation is the reachable equivalent. It proves
#: the assertion is evaluated against real data and reaches a real verdict,
#: which is the property that was actually in doubt.
MUTATIONS = [
    ("resolver expectation",
     "asserts the resolver does NOT serve the anchored run",
     "    check(run_id in servable,",
     "    check(run_id not in servable,"),

    ("finalisation requirement",
     "asserts the plan-required stages are anything BUT success",
     '    missing = [s for s in plan.required if stages.get(s) != "success"]',
     '    missing = [s for s in plan.required if stages.get(s) == "success"]'),

    ("run anchoring",
     "attributes every row to a run that is not the anchored one",
     "        SELECT asx_code, compute_run_id FROM screener.universe\n"
     "         WHERE asx_code = ANY(%s);\"\"\", (codes,))\n"
     "    return dict(cur.fetchall())",
     "        SELECT asx_code, -1 FROM screener.universe\n"
     "         WHERE asx_code = ANY(%s);\"\"\", (codes,))\n"
     "    return dict(cur.fetchall())"),

    ("batch surface",
     "asserts the batch response contains a different number of rows",
     "    check(len(rows) == len(codes),",
     "    check(len(rows) != len(codes),"),

    ("ordering exclusion",
     "asserts the ranking admits a DIFFERENT count from the applicable one",
     "    check(ranked == applicable,",
     "    check(ranked != applicable,"),

    ("governed projection",
     "treats every served governed value as an unexplained blank",
     "                if value is None:\n"
     "                    blank += 1",
     "                if value is not None:\n"
     "                    blank += 1"),
]


BACKEND = GATE.parent.parent


def run(path: Path, run_id: int | None) -> tuple[int, str]:
    """Run a copy of the gate with backend importable.

    PYTHONPATH is the whole point. The mutated copy lives in a temp directory,
    and a script's sys.path[0] is its OWN directory, not the working one — so
    `sys.path.insert(0, parents[1])` inside the gate resolves to /tmp and
    `import app.main` fails. Every mutated run would then exit non-zero on
    ImportError, and this harness would report all five mutations as caught
    without a single assertion having been evaluated: the inert-guard failure
    mode wearing a different hat, and this time it would have certified the
    gate rather than a product defect.
    """
    argv = [sys.executable, str(path)]
    if run_id is not None:
        argv += ["--run-id", str(run_id)]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(argv, capture_output=True, text=True,
                          cwd=str(BACKEND), env=env)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, default=None)
    args = parser.parse_args()

    original = GATE.read_text(encoding="utf-8")

    # The baseline is not decoration. A mutation that "causes a failure" on a
    # gate that was already failing has demonstrated nothing about the
    # mutation.
    print("baseline (unmutated gate must PASS)")
    code, output = run(GATE, args.run_id)
    if code != 0:
        print(output)
        print("\nBASELINE FAILED — fix the gate or the publication first. "
              "Mutation results against a red baseline are meaningless.")
        return 1
    print("  PASS  the unmutated gate exits 0\n")

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, effect, old, new in MUTATIONS:
            target = Path(tmp) / "gate_b.py"
            if original.count(old) != 1:
                failures.append(name)
                print(f"  INERT {name} — the fragment matches "
                      f"{original.count(old)} times, not once. The mutation "
                      f"was never applied, so its PASS would be a lie.")
                continue
            target.write_text(original.replace(old, new), encoding="utf-8")
            shutil.copystat(GATE, target)

            code, output = run(target, args.run_id)

            # Non-zero is not enough. A mutated copy that cannot import, or
            # dies on an UndefinedColumn, also exits non-zero — and would be
            # scored as "the assertion caught it" when no assertion ran at
            # all. The gate prints this line only after evaluating every
            # assertion and finding at least one breach, so it is the only
            # evidence that the mutation was detected rather than merely fatal.
            detected = code != 0 and "GATE B FAILED" in output
            crashed = code != 0 and not detected
            if not detected:
                failures.append(name)
            verdict = ("caught" if detected
                       else "CRASHED, assertion never evaluated" if crashed
                       else "SURVIVED")
            print(f"  {'PASS' if detected else 'FAIL'}  {name}: "
                  f"{verdict} — {effect}")
            if crashed:
                print("        " + (output.strip().splitlines() or ["(no output)"])[-1])
            elif not detected:
                print("        the gate exited 0 with this assertion "
                      "disabled, so it was never proving it")

    print()
    if failures:
        print(f"MUTATION TESTING FAILED — {len(failures)} assertion(s) do not "
              f"hold their claim: {failures}")
        return 1
    print(f"MUTATION TESTING PASSED — all {len(MUTATIONS)} assertions fail "
          f"when the thing they assert is broken")
    return 0


if __name__ == "__main__":
    sys.exit(main())
