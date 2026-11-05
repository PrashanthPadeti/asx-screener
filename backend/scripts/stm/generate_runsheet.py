"""
The job execution run sheet, extracted from the jobs
====================================================
Deliverable #3: every job in every layer, in execution order, with its
dependencies, what may run beside it, and what it reads and writes.

Four declared sources, joined. None of it is typed from memory:

    app/scheduler_registry.py       every scheduler.add_job and its trigger
    scripts/eodhd/v2/jobs/*.py      ordered steps, fatal vs non-fatal
    compute/engine/run_plans.py     the canonical plans and their stages
    scripts/p0a_canonical_run.py    stage name -> the argv actually run
    database/stm/lineage.json       what each module reads and writes

Dependencies are DERIVED, not declared
--------------------------------------
Two kinds of edge, and they are different claims:

    sequence   step N+1 follows step N inside one pipeline. An ordering the
               author chose. It may or may not be a real data dependency.
    data       job B reads a table job A writes. A dependency that exists
               whether or not anyone wrote it down.

Reporting only the first would describe the script; reporting only the second
would lose the ingestion barrier, which is a real constraint that no table
lineage expresses. Both are emitted, labelled, so a reader can see which
orderings are load-bearing and which are merely historical.

What can run in parallel is then the complement: two jobs may run together
when neither can reach the other through data edges. That is computed, and it
is a STATEMENT ABOUT DATA ONLY -- it does not account for the execution lease,
API rate budgets, or the 4GB of RAM on the box. Those are noted per job where
known, and the sheet says so rather than implying a free hand.

Usage:
    cd backend && python scripts/stm/generate_runsheet.py \
        --lineage ../database/stm/lineage.json \
        --out-dir ../database/stm

Exit codes:  0 run sheet written
             2 could not run (no lineage, no jobs found) -- never silent
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

REGISTRY  = BACKEND / "app/scheduler_registry.py"
RUN_PLANS = BACKEND / "compute/engine/run_plans.py"
DRIVER    = BACKEND / "scripts/p0a_canonical_run.py"
PIPELINES = {
    "daily":   BACKEND / "scripts/eodhd/v2/jobs/daily_pipeline.py",
    "weekly":  BACKEND / "scripts/eodhd/v2/jobs/weekly_pipeline.py",
    "monthly": BACKEND / "scripts/eodhd/v2/jobs/monthly_pipeline.py",
}

#: Calls that run a pipeline step, and whether a failure stops the pipeline.
#: run_optional exists precisely so a scraping failure cannot block prices,
#: and a run sheet that flattened the two would misreport every recovery path.
STEP_CALLS = {"run": True, "run_optional": False}


# ── Pipeline steps ───────────────────────────────────────────────────────────

def _str_of(node) -> str | None:
    """A string from a literal, or from str(X / 'name.py') path building."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "str":
        return _str_of(node.args[0]) if node.args else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = _str_of(node.left), _str_of(node.right)
        if right:
            return f"{left}/{right}" if left else right
    if isinstance(node, ast.Name):
        return f"${node.id}"
    if isinstance(node, ast.Attribute):
        return f"${node.attr}"
    return None


def _loop_bindings(tree: ast.AST, call: ast.Call) -> list:
    """Variable bindings under which `call` executes, one dict per iteration.

    Handles the one shape the pipelines actually use:
        for a, b in ((1, "x"), (2, "y")): ... f(a, b)
    A call outside such a loop yields a single empty binding, so the caller
    treats both cases identically.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        if not any(n is call for n in ast.walk(node)):
            continue
        try:
            rows = ast.literal_eval(node.iter)
        except (ValueError, TypeError):
            continue
        names = ([t.id for t in node.target.elts
                  if isinstance(t, ast.Name)]
                 if isinstance(node.target, ast.Tuple)
                 else [node.target.id] if isinstance(node.target, ast.Name)
                 else [])
        if not names:
            continue
        out = []
        for row in rows:
            values = row if isinstance(row, (tuple, list)) else (row,)
            if len(values) == len(names):
                out.append(dict(zip(names, values)))
        if out:
            return out
    return [{}]


def _skip_args(call: ast.Call, binding: dict):
    """(step number, label) for one skip_step call under one binding."""
    first, second = call.args[0], call.args[1]

    number = getattr(first, "value", None)
    if number is None and isinstance(first, ast.Name):
        number = binding.get(first.id)

    label = _str_of(second)
    if label is None and isinstance(second, ast.JoinedStr):
        parts = []
        for piece in second.values:
            if isinstance(piece, ast.Constant):
                parts.append(str(piece.value))
            elif isinstance(piece, ast.FormattedValue) and \
                    isinstance(piece.value, ast.Name):
                parts.append(str(binding.get(piece.value.id, "")))
        label = "".join(parts).strip() or None
    if label is None and isinstance(second, ast.Name):
        label = binding.get(second.id)

    return number, label


def _kw(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def pipeline_steps(path: Path) -> list:
    """Ordered steps of one pipeline, in source order."""
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    steps = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue

        fn = node.func.id
        if fn in STEP_CALLS and node.args:
            label = _str_of(node.args[0])
            if not label:
                continue
            argv = []
            if len(node.args) > 1 and isinstance(node.args[1], ast.List):
                argv = [_str_of(e) or "?" for e in node.args[1].elts]
            step_no = _kw(node, "step")
            steps.append({
                "line":    node.lineno,
                "step":    getattr(step_no, "value", None),
                "label":   label,
                "script":  next((a for a in argv
                                 if isinstance(a, str) and a.endswith(".py")), None),
                "argv":    argv,
                "fatal":   STEP_CALLS[fn],
                "status":  "runs",
            })
        elif fn == "skip_step" or (isinstance(node.func, ast.Attribute)
                                   and node.func.attr == "skip_step"):
            pass
    # skip_step is read separately: it is an attribute call on the tracker.
    # Some are inside a `for step, name in ((5, "..."), (7, "..."))` loop, so
    # the arguments are loop variables rather than literals. Those are
    # expanded from the loop's own literal iterable -- six steps of the daily
    # pipeline live in exactly that shape, and reading only literal arguments
    # collapsed all six into one nameless row. A step that vanishes from a run
    # sheet is indistinguishable from a step that does not exist.
    unresolved = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "skip_step" and len(node.args) >= 2):
            for binding in _loop_bindings(tree, node):
                number, label = _skip_args(node, binding)
                if number is None and label is None:
                    unresolved.append(node.lineno)
                    continue
                steps.append({
                    "line":   node.lineno,
                    "step":   number,
                    "label":  label or "",
                    "script": None,
                    "argv":   [],
                    "fatal":  False,
                    "status": "skipped — " + (
                        (label or "").split("—", 1)[1].strip()
                        if "—" in (label or "") else "see source"),
                })
    for lineno in unresolved:
        steps.append({
            "line": lineno, "step": None,
            "label": f"UNRESOLVED skip_step at line {lineno}",
            "script": None, "argv": [], "fatal": False,
            "status": "unresolved — arguments are not statically knowable",
        })
    steps.sort(key=lambda s: s["line"])
    return _merge_conditional_branches(steps)


def _merge_conditional_branches(steps: list) -> list:
    """One row per step, not one row per branch.

    `if not args.skip_download: run(...) else: tracker.skip_step(...)` is a
    single step with a condition on it. Walking the AST sees both arms and
    emitted step 1 twice -- once "runs", once "skipped" -- which reads as two
    executions of the same step in sequence. A run sheet that cannot be
    followed literally is worse than none, because somebody will follow it.

    Steps without a number (none at present) cannot be merged this way and are
    passed through untouched rather than collapsed onto each other.
    """
    merged, by_step = [], {}
    for step in steps:
        key = step["step"]
        if key is None:
            merged.append(step)
            continue
        if key not in by_step:
            by_step[key] = step
            merged.append(step)
            continue

        first, second = by_step[key], step
        runs = next((s for s in (first, second) if s["status"] == "runs"), None)
        skip = next((s for s in (first, second) if s["status"] != "runs"), None)
        if runs is None or skip is None:
            # Two genuine executions of one step number: a defect in the
            # pipeline, not something to hide by merging.
            merged.append(step)
            continue

        first.update({
            "script":    runs["script"],
            "argv":      runs["argv"],
            "fatal":     runs["fatal"],
            "status":    "conditional",
            "condition": f"runs at line {runs['line']}, "
                         f"skipped at line {skip['line']}",
        })
    return merged


# ── Scheduler registry ───────────────────────────────────────────────────────

def scheduler_jobs() -> list:
    """Every scheduler.add_job, with its trigger rendered as text."""
    if not REGISTRY.exists():
        return []
    tree = ast.parse(REGISTRY.read_text(encoding="utf-8"))
    jobs = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_job"):
            continue

        name, target = None, None
        if node.args:
            first = node.args[0]
            if isinstance(first, ast.Call):
                if first.args and isinstance(first.args[0], ast.Constant):
                    name = first.args[0].value
                if len(first.args) > 1:
                    target = _str_of(first.args[1]) or getattr(
                        first.args[1], "id", None)
            else:
                target = getattr(first, "id", None)

        trigger = None
        for arg in node.args[1:]:
            if isinstance(arg, ast.Call) and getattr(arg.func, "id", "") == "CronTrigger":
                parts = {k.arg: getattr(k.value, "value", "?") for k in arg.keywords}
                trigger = "cron(" + ", ".join(
                    f"{k}={v}" for k, v in parts.items()) + ")"
        if trigger is None:
            t = _kw(node, "trigger")
            if isinstance(t, ast.Constant):
                every = {k.arg: getattr(k.value, "value", "?")
                         for k in node.keywords if k.arg in
                         ("seconds", "minutes", "hours")}
                trigger = f"{t.value}(" + ", ".join(
                    f"{k}={v}" for k, v in every.items()) + ")"
        jobs.append({"name": name or target or f"line {node.lineno}",
                     "target": target, "trigger": trigger or "unknown",
                     "line": node.lineno})
    jobs.sort(key=lambda j: j["line"])
    return jobs


# ── Canonical plans ──────────────────────────────────────────────────────────

def canonical_plans() -> dict:
    """Plan name -> {stages, required, reuses, executable}."""
    if not RUN_PLANS.exists():
        return {}
    tree = ast.parse(RUN_PLANS.read_text(encoding="utf-8"))
    plans = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "id", "") == "RunPlan"):
            continue
        fields = {}
        for kw in node.value.keywords:
            try:
                fields[kw.arg] = ast.literal_eval(kw.value)
            except ValueError:
                fields[kw.arg] = "<computed>"
        target = node.targets[0]
        if isinstance(target, ast.Name):
            plans[target.id] = fields
    return plans


def stage_commands() -> dict:
    """Stage name -> the script the driver actually runs."""
    if not DRIVER.exists():
        return {}
    tree = ast.parse(DRIVER.read_text(encoding="utf-8"))
    out = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") == "STAGE_COMMANDS"
                        for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            stage = getattr(key, "value", None)
            script = None
            if isinstance(value, ast.Lambda) and isinstance(value.body, ast.List):
                for element in value.body.elts:
                    s = _str_of(element)
                    if s and s.endswith(".py"):
                        script = s
                        break
            out[stage] = script
    return out


# ── Dependency derivation ────────────────────────────────────────────────────

def data_edges(lineage: dict, modules: list) -> dict:
    """module -> set of modules it depends on, because it reads their output."""
    writer_of = defaultdict(set)
    for table, info in lineage.get("by_table", {}).items():
        for w in info["written_by"]:
            writer_of[table].add(w["module"])

    deps = {m: set() for m in modules}
    for module in modules:
        info = lineage.get("by_module", {}).get(module)
        if not info:
            continue
        for table in info["reads"]:
            for producer in writer_of.get(table, ()):
                if producer != module and producer in deps:
                    deps[module].add(producer)
    return deps


def parallel_levels(deps: dict) -> dict:
    """Topological level per module. Same level == no data edge between them.

    Kahn's algorithm. A cycle is reported rather than resolved: a cyclic
    dependency between two producers is a real finding about the pipeline,
    not something a run sheet should quietly linearise.
    """
    indegree = {m: len(d) for m, d in deps.items()}
    dependents = defaultdict(set)
    for m, d in deps.items():
        for p in d:
            dependents[p].add(m)

    level, queue = {}, deque(m for m, n in indegree.items() if n == 0)
    for m in queue:
        level[m] = 0
    while queue:
        m = queue.popleft()
        for child in dependents[m]:
            indegree[child] -= 1
            level[child] = max(level.get(child, 0), level[m] + 1)
            if indegree[child] == 0:
                queue.append(child)

    for m in deps:
        if m not in level:
            level[m] = -1                 # in a cycle; reported, not hidden
    return level


# ── Emit ─────────────────────────────────────────────────────────────────────

RUNSHEET_COLUMNS = [
    "seq", "cadence", "step", "layer", "job_name", "script",
    "schedule_or_trigger", "status", "on_failure",
    "reads", "writes", "depends_on_data", "parallel_level", "notes",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lineage", default=str(BACKEND.parent / "database/stm/lineage.json"))
    ap.add_argument("--out-dir", default=str(BACKEND.parent / "database/stm"))
    args = ap.parse_args()

    lineage_path = Path(args.lineage)
    if not lineage_path.exists():
        print(f"2  lineage not found at {lineage_path}; run extract_lineage.py "
              f"first. Without it every job would report no dependencies, "
              f"which reads exactly like a pipeline that has none")
        return 2
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))

    plans   = canonical_plans()
    stages  = stage_commands()
    sched   = scheduler_jobs()
    modules = sorted(lineage.get("by_module", {}))
    if not modules:
        print("2  lineage graph has no modules — nothing to sequence")
        return 2

    deps   = data_edges(lineage, modules)
    levels = parallel_levels(deps)

    def module_for(script: str | None) -> str | None:
        if not script:
            return None
        tail = script.split("/")[-1]
        hits = [m for m in modules if m.endswith("/" + tail) or m == tail]
        return hits[0] if len(hits) == 1 else (hits[0] if hits else None)

    def facts(script: str | None) -> dict:
        module = module_for(script)
        info = lineage.get("by_module", {}).get(module) if module else None
        writes = sorted(info["writes"]) if info else []
        reads  = info["reads"] if info else []
        layers = {lineage["by_table"].get(t, {}).get("layer") for t in writes}
        layers.discard(None)
        return {"module": module, "writes": writes, "reads": reads,
                "layer": "/".join(sorted(layers)) if layers else "",
                "level": levels.get(module, "")}

    rows, seq = [], 0

    for cadence, path in PIPELINES.items():
        for step in pipeline_steps(path):
            seq += 1
            f = facts(step["script"])
            rows.append({
                "seq": seq, "cadence": cadence, "step": step["step"] or "",
                "layer": f["layer"], "job_name": step["label"],
                "script": step["script"] or "",
                "schedule_or_trigger": f"{cadence} pipeline (cron)",
                "status": step["status"],
                "on_failure": "ABORT pipeline" if step["fatal"]
                              else "log and continue (non-fatal)",
                "reads": "; ".join(f["reads"][:12]),
                "writes": "; ".join(f["writes"]),
                "depends_on_data": "; ".join(
                    sorted(Path(d).name for d in deps.get(f["module"], ()))),
                "parallel_level": f["level"],
                "notes": step.get("condition", ""),
            })

    for plan_name, plan in plans.items():
        if plan.get("executable") is False:
            continue
        for order, stage in enumerate(plan.get("stages", ()), start=1):
            seq += 1
            script = stages.get(stage)
            f = facts(script)
            required = stage in plan.get("required", ())
            rows.append({
                "seq": seq, "cadence": f"plan:{plan_name}", "step": order,
                "layer": f["layer"], "job_name": f"stage {stage}",
                "script": script or "",
                "schedule_or_trigger": "canonical driver, under execution lease",
                "status": "runs" if required else "runs (not required to publish)",
                "on_failure": "REFUSE publication" if required
                              else "publication may still proceed",
                "reads": "; ".join(f["reads"][:12]),
                "writes": "; ".join(f["writes"]),
                "depends_on_data": "; ".join(
                    sorted(Path(d).name for d in deps.get(f["module"], ()))),
                "parallel_level": f["level"],
                "notes": ("reused, not recomputed"
                          if stage in plan.get("reuses", ()) else ""),
            })

    for job in sched:
        seq += 1
        rows.append({
            "seq": seq, "cadence": "scheduler", "step": "",
            "layer": "", "job_name": job["name"], "script": job["target"] or "",
            "schedule_or_trigger": job["trigger"], "status": "runs",
            "on_failure": "see job telemetry", "reads": "", "writes": "",
            "depends_on_data": "", "parallel_level": "",
            "notes": f"app/scheduler_registry.py:{job['line']}",
        })

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "job_execution_runsheet.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RUNSHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    cycles = [m for m, lv in levels.items() if lv == -1]
    by_level = defaultdict(list)
    for m, lv in levels.items():
        if lv >= 0:
            by_level[lv].append(Path(m).name)

    print(f"run sheet written: {csv_path}")
    print(f"  rows               {len(rows)}")
    print(f"  pipelines          {len([p for p in PIPELINES.values() if p.exists()])}")
    print(f"  canonical plans    {len([p for p in plans.values() if p.get('executable') is not False])}")
    print(f"  scheduler jobs     {len(sched)}")
    print(f"  parallel levels    {len(by_level)}")
    for lv in sorted(by_level):
        names = sorted(by_level[lv])
        print(f"    level {lv}: {len(names):3} module(s)  "
              f"{', '.join(names[:6])}{' ...' if len(names) > 6 else ''}")
    if cycles:
        print(f"  WARNING {len(cycles)} module(s) in a dependency cycle, "
              f"reported rather than linearised: {sorted(Path(c).name for c in cycles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
