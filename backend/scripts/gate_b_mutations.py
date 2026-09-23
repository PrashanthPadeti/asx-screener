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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent / "gate_b.py"

#: (name, what it breaks, exact source fragment, replacement)
MUTATIONS = [
    ("resolver expectation",
     "accepts a resolver that does NOT serve the anchored run",
     "    check(run_id in servable,",
     "    check(run_id not in servable or True,"),

    ("finalisation requirement",
     "accepts a run whose plan-required stages are not SUCCESS",
     '    missing = [s for s in plan.required if stages.get(s) != "success"]',
     "    missing = []"),

    ("run anchoring",
     "measures the newest finalised run instead of the anchored one",
     "        SELECT asx_code, compute_run_id FROM screener.universe\n"
     "         WHERE asx_code = ANY(%s);\"\"\", (codes,))\n"
     "    return dict(cur.fetchall())",
     "        SELECT asx_code, -1 FROM screener.universe\n"
     "         WHERE asx_code = ANY(%s);\"\"\", (codes,))\n"
     "    return dict(cur.fetchall())"),

    ("governed projection",
     "tolerates an attributed row whose governed value is blank and unexplained",
     "                    blank += 1\n"
     "                    breaches.append(f\"{code}: {metric} is null with no \"\n"
     "                                    f\"sidecar entry\")",
     "                    blank += 1"),
]


def run(path: Path, run_id: int | None) -> tuple[int, str]:
    argv = [sys.executable, str(path)]
    if run_id is not None:
        argv += ["--run-id", str(run_id)]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          cwd=str(GATE.parent.parent))
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
            survived = code == 0
            if survived:
                failures.append(name)
            print(f"  {'FAIL' if survived else 'PASS'}  {name}: "
                  f"{'SURVIVED' if survived else 'caught'} — {effect}")
            if survived:
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
