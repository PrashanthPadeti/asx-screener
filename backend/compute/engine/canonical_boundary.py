"""
Where the canonical driver's ownership begins and ends
======================================================
`docs/canonical_orchestration.md` freezes the rule; this module is its
executable form.

    Can this step mutate a table whose state can affect one of the 72 governed
    values?

A hand-maintained answer to that question is true when written and stops being
true silently. This codebase has already paid for exactly that: the discovery
clone's exclusion list was derived from the code when plans had four stages,
and `transform_prices` -- which reads `staging_au.eod_prices` -- killed Cycle A
1.4 seconds in once plans had eight. So the boundary is DERIVED, on every run,
from the SQL the stages actually contain.

Three sets, all computed
------------------------
    canonical_outputs   tables a plan stage WRITES. The driver owns these.
    canonical_inputs    tables a plan stage reads but never writes. Ingestion
                        may fill them; nothing downstream may touch them.
    dependency_tables   the union — everything whose state can reach a
                        governed value.

Direction is not decoration. It is the whole difference between the two
classifications that are allowed to exist outside the driver:

    PRE_INGESTION     may write canonical INPUTS (that is its job) but never
                      canonical OUTPUTS, which the driver owns.
    POST_PUBLICATION  may READ anything, including the published universe, and
                      write its own downstream artifacts — but may not write
                      ANY dependency table. Writing an input after publication
                      moves the sources out from under a contract that has
                      already been finalised against them.
    POST_PUBLICATION_WRITER
                      the narrow exception: a suffix step that writes a shared
                      canonical table, permitted only inside the lease, only
                      after finalisation, and only on NON-GOVERNED columns —
                      which is checked, not claimed. Every one states why.
    CANONICAL_DRIVER  owns the derived mutation sequence, admission through
                      finalisation. Not declared: a step whose script IS a
                      plan stage is one of these by definition.

Ownership stays at TABLE level deliberately. Making it column-level would put
correctness on two independent writers keeping perfectly disjoint SET lists
forever, and this codebase has enough evidence that such assumptions decay.
The invariant is: while a canonical execution owns screener.universe, no
unrelated writer mutates it concurrently. POST_PUBLICATION_WRITER does not
weaken that — it sequences the writer inside the lease instead of exempting
it.

Pure stdlib by design. It reads source; it imports nothing that needs a
database driver, so it runs in any environment and cannot be quietly skipped
for want of an install.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

# So `python compute/engine/canonical_boundary.py` works from anywhere. The
# report is meant to be run by hand while deciding a classification, not only
# through pytest.
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from compute.engine.run_plans import PLANS  # noqa: E402
DRIVER = BACKEND / "scripts" / "p0a_canonical_run.py"
JOBS = BACKEND / "scripts" / "eodhd" / "v2" / "jobs"

#: Schemas whose tables can carry state into a governed value. `users` is
#: deliberately absent: it holds accounts and sessions, nothing the factor
#: model reads.
SCHEMAS = ("financials", "market", "staging_au", "screener")

_TABLE = rf"(?:{'|'.join(SCHEMAS)})\.\w+"

#: Verb -> direction. Order matters inside the alternation: `DELETE FROM` and
#: `INSERT INTO` must be tried before the bare `FROM`/`INTO` they contain, or a
#: deletion is recorded as a read and the step looks harmless.
_VERBS = [
    ("INSERT INTO", "w"), ("DELETE FROM", "w"), ("TRUNCATE TABLE", "w"),
    ("TRUNCATE", "w"), ("UPDATE", "w"), ("COPY", "w"),
    ("FROM", "r"), ("JOIN", "r"),
]
_PATTERN = re.compile(
    r"\b(" + "|".join(v.replace(" ", r"\s+") for v, _ in _VERBS) + r")\s+"
    + f"({_TABLE})", re.IGNORECASE)
_DIRECTION = {v.lower(): d for v, d in _VERBS}


def _executable_source(path: Path) -> str:
    """Source with docstrings and comments removed.

    Not fastidiousness. A guard in this repo once matched
    `discovery_fault("after_provisional_rebuild")` in a module's own DOCSTRING
    and concluded the call was present; it would have passed just as happily
    with the real call deleted. Prose about a table is not a reference to it,
    and this module's whole output is a claim about which tables a file
    touches.
    """
    src = path.read_text(encoding="utf-8", errors="ignore")

    # Docstring removal needs a parse; comment removal must NOT depend on one.
    # The first draft returned raw source on SyntaxError, so an unparseable
    # file — a .sql file, or a .py this module is asked about before it is
    # valid — kept every commented-out statement and reported tables the code
    # does not touch.
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    src = src.replace(doc, "")

    # `--` matters as much as `#`: these files carry SQL in triple-quoted
    # strings, and a commented-out UPDATE inside one is not a write.
    return "\n".join(line for line in src.splitlines()
                     if not line.strip().startswith(("#", "--")))


_SET_LIST = re.compile(
    rf"\bUPDATE\s+({_TABLE})\s+SET\s+(.*?)(?=\bFROM\b|\bWHERE\b|\bRETURNING\b|;|\"\"\")",
    re.IGNORECASE | re.DOTALL)
_INSERT_LIST = re.compile(
    rf"\bINSERT\s+INTO\s+({_TABLE})\s*\(([^)]*)\)", re.IGNORECASE | re.DOTALL)
_ASSIGNED = re.compile(r"(\w+)\s*=")


def columns_written(path: Path, table: str) -> set[str]:
    """Which columns of `table` a script assigns.

    Used for one thing: holding a POST_PUBLICATION_WRITER to its claim that it
    touches no governed column. The claim is cheap to make and expensive to be
    wrong about, so it is checked rather than believed.

    Deliberately narrow — `UPDATE ... SET` and `INSERT INTO ... (cols)`, the
    two shapes these writers use. It is not a SQL parser, and a writer whose
    shape it cannot read reports NO columns, which is why
    `test_the_column_extractor_finds_pros_and_cons` exists: an extractor that
    silently finds nothing would clear every writer it cannot understand.
    """
    source = _executable_source(path)
    found: set[str] = set()
    for matched_table, body in _SET_LIST.findall(source):
        if matched_table.lower() == table.lower():
            found |= set(_ASSIGNED.findall(body))
    for matched_table, body in _INSERT_LIST.findall(source):
        if matched_table.lower() == table.lower():
            found |= {c.strip() for c in body.split(",") if c.strip().isidentifier()}
    return found


def governed_columns() -> set[str]:
    """The storage columns the current model governs, from the writer itself."""
    from compute.engine.metric_states import LATEST_MODEL_VERSION
    from compute.engine.universe_writer import persisted_governed
    return set(persisted_governed(LATEST_MODEL_VERSION).values())


def tables_touched(path: Path) -> dict[str, set[str]]:
    """{table: {'r', 'w'}} for one script."""
    found: dict[str, set[str]] = {}
    for verb, table in _PATTERN.findall(_executable_source(path)):
        key = " ".join(verb.split()).lower()
        found.setdefault(table.lower(), set()).add(_DIRECTION[key])
    return found


# ── The plan side: what the driver owns ──────────────────────────────────────

def stage_scripts() -> dict[str, Path]:
    """stage name -> the script the driver runs for it.

    Read out of STAGE_COMMANDS by AST rather than by importing the driver,
    which needs psycopg2. `test_canonical_boundary` asserts this parse against
    the real import wherever the driver is importable, so the convenience
    cannot drift into a second source of truth.
    """
    tree = ast.parse(DRIVER.read_text(encoding="utf-8"))
    mapping: dict[str, Path] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign)
                and any(getattr(t, "id", "") == "STAGE_COMMANDS"
                        for t in node.targets)):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            stage = ast.literal_eval(key)
            for sub in ast.walk(value):
                if (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                        and sub.value.endswith(".py")):
                    mapping[stage] = BACKEND / sub.value
                    break
    return mapping


#: The canonical tail. It is invoked separately, after the fault seam, so it is
#: deliberately absent from STAGE_COMMANDS — but it is the step that writes the
#: governed columns, and a boundary that left it out would be describing a
#: driver that does not publish.
TAIL_SCRIPT = BACKEND / "compute" / "engine" / "composite_score.py"


def plan_scripts() -> dict[str, Path]:
    """Every script any plan can run, including the tail."""
    commands = stage_scripts()
    scripts = {"composite_score": TAIL_SCRIPT}
    for plan in PLANS.values():
        for stage in plan.stages:
            if stage in commands:
                scripts[stage] = commands[stage]
    return scripts


def canonical_tables() -> tuple[set[str], set[str]]:
    """(inputs, outputs). Outputs are written by a stage; inputs only read."""
    reads: set[str] = set()
    writes: set[str] = set()
    for path in plan_scripts().values():
        for table, directions in tables_touched(path).items():
            if "w" in directions:
                writes.add(table)
            if "r" in directions:
                reads.add(table)
    return reads - writes, writes


def dependency_tables() -> set[str]:
    inputs, outputs = canonical_tables()
    return inputs | outputs


# ── The pipeline side: what the wrappers do ──────────────────────────────────

@dataclass(frozen=True)
class Step:
    pipeline: str
    label: str
    script: Path

    @property
    def key(self) -> str:
        """How a step is named in CLASSIFICATIONS: its script, repo-relative.

        Keyed by script rather than by label because labels are prose and get
        reworded. Two pipelines running the same script get the same
        classification, which is correct: the question is what the script
        touches.
        """
        return self.script.relative_to(BACKEND).as_posix()


_PATH_NAMES = {"SCRIPTS": "scripts/eodhd/v2",
               "COMPUTE": "compute/engine",
               "ASIC": "scripts/asic",
               "BASE_DIR": ""}


def _resolve(node: ast.AST, source: str) -> Path | None:
    """`str(SCRIPTS / "transforms" / "transform_prices.py")` -> a real path."""
    segment = ast.get_source_segment(source, node) or ""
    if ".py" not in segment:
        return None
    root = next((v for k, v in _PATH_NAMES.items()
                 if re.search(rf"\b{k}\b", segment)), None)
    if root is None:
        return None
    parts = re.findall(r'"([^"]+)"', segment)
    if not parts:
        return None
    return BACKEND / root / "/".join(parts) if root else BACKEND / "/".join(parts)


def pipeline_steps(pipeline: str) -> list[Step]:
    """Every script a pipeline invokes through run()/run_optional()."""
    path = JOBS / pipeline
    source = path.read_text(encoding="utf-8")
    steps: list[Step] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") in ("run", "run_optional")
                and len(node.args) >= 2):
            continue
        label = (node.args[0].value
                 if isinstance(node.args[0], ast.Constant) else "?")
        for element in getattr(node.args[1], "elts", []):
            script = _resolve(element, source)
            if script is not None:
                steps.append(Step(pipeline, label, script))
                break
    return steps


PIPELINES = ("daily_pipeline.py", "weekly_pipeline.py", "monthly_pipeline.py")


# ── Units cron launches directly ─────────────────────────────────────────────
#
# A pipeline is not the only launch authority. cron runs scripts of its own,
# and a boundary that saw only pipeline steps was an authority over the
# pipelines and silent about everything else — including a script that writes
# a canonical output on its own schedule.
#
# Only the TARGETS are derived here, from the checked-in generator. Whether
# desired and observed state agree, and whether a launch sits outside the
# lease, belong to `launch_authority` — this module answers one question, and
# it is "what may this unit touch?".

GENERATOR = JOBS / "setup_cron.sh"

_CADENCE = r"(?:[-\d*/,]+\s+){4}[-\d*/,]+"
_CRON_ASSIGN = re.compile(r'^(\w+_CMD)="(.*)"\s*$', re.MULTILINE)
_SHELL_VAR = re.compile(r'^(\w+)="(.*)"\s*$', re.MULTILINE)


def cron_target(command: str) -> str:
    """The script a cron command runs, repo-relative ('' if none)."""
    module = re.search(r"-m\s+([\w.]+)", command)
    if module:
        return "backend/" + module.group(1).replace(".", "/") + ".py"
    script = re.search(r"([\w./-]+\.(?:py|sh))",
                       command.replace("/opt/asx-screener/", ""))
    return script.group(1).lstrip("./") if script else ""


def cron_units() -> dict[str, Path]:
    """{classification key: script} for everything the generator schedules.

    Pipelines are excluded: they are wrappers, and their steps are already
    units in their own right.
    """
    text = GENERATOR.read_text(encoding="utf-8")
    variables = dict(_SHELL_VAR.findall(text))
    wrappers = {f"scripts/eodhd/v2/jobs/{p}" for p in PIPELINES}
    units: dict[str, Path] = {}
    for name, value in _CRON_ASSIGN.findall(text):
        for _ in range(4):
            value = re.sub(r"\$\{(\w+)\}",
                           lambda m: variables.get(m.group(1), m.group(0)),
                           value)
        target = cron_target(value)
        if not target:
            continue
        key = target[len("backend/"):] if target.startswith("backend/") else target
        if key in wrappers:
            continue
        path = BACKEND.parent / target
        if path.exists():
            units[key] = path
    return units


#: Units this module cannot derive but that another launch authority knows
#: about — populated by `launch_authority` from the OBSERVED crontab, which
#: only exists on the server. Empty elsewhere, so the derived answer is the
#: same everywhere except where it can legitimately be larger.
EXTRA_UNITS: dict[str, Path] = {}


def all_units() -> dict[str, Path]:
    """Every launchable unit whose table access this module judges."""
    units = {s.key: s.script for s in all_steps()}
    units.update(cron_units())
    units.update(EXTRA_UNITS)
    return units


def all_steps() -> list[Step]:
    return [s for p in PIPELINES for s in pipeline_steps(p)]


# ── The declaration ──────────────────────────────────────────────────────────

PRE_INGESTION = "PRE_INGESTION"
POST_PUBLICATION = "POST_PUBLICATION"
POST_PUBLICATION_WRITER = "POST_PUBLICATION_WRITER"
CANONICAL_DRIVER = "CANONICAL_DRIVER"

#: A suffix step that writes a canonical table, permitted only under the
#: canonical execution lease and only on non-governed columns.
#:
#: Table ownership stays the invariant — "while a canonical execution owns
#: screener.universe, no unrelated writer mutates it concurrently" — precisely
#: because the column-level alternative would make correctness depend on two
#: independent writers keeping perfectly disjoint SET lists forever. This
#: classification does not weaken that. It says: this writer is sequenced
#: inside the lease, and its non-governed claim is checked rather than
#: asserted.
#:
#: Every entry states why. The reason is not documentation — a writer with no
#: stated reason is a violation.
SUFFIX_WRITE_REASONS: dict[str, str] = {
    "compute/engine/pros_cons.py":
        "Writes shared canonical table screener.universe; non-governed "
        "columns (pros, cons). Decided 24 Sep 2026: it determines none of the "
        "72 governed values, so its success must NOT gate canonical "
        "finalisation — a failure leaves the published run authoritative and "
        "reports suffix-specific degradation. But it mutates the table the "
        "driver owns, so it runs after finalisation and inside the lease. "
        "Mechanically established before deciding: no plan stage reads pros "
        "or cons, so it has no reason to execute before publication.",
}

#: Steps that touch a dependency table and are NOT plan stages must be declared
#: here. A step whose script is a plan stage needs no entry — it is
#: CANONICAL_DRIVER by derivation, and declaring it would invite the two to
#: disagree.
#:
#: An unclassified intersection fails the test rather than defaulting to
#: anything. Defaulting is how a new step that quietly writes a governed input
#: becomes invisible.
CLASSIFICATIONS: dict[str, str] = {
    # Ingestion. Each writes a canonical INPUT — a table plan stages read and
    # never write — which is exactly what PRE_INGESTION is for. Reading an
    # output (weekly/monthly read market.daily_prices) is unrestricted.
    "scripts/eodhd/v2/download_eod_prices.py": PRE_INGESTION,
    "scripts/eodhd/v2/load_to_staging_prices.py": PRE_INGESTION,
    "scripts/eodhd/v2/load_to_staging_fundamentals.py": PRE_INGESTION,
    "scripts/eodhd/v2/transforms/transform_valuation.py": PRE_INGESTION,
    "scripts/eodhd/v2/transforms/transform_analyst_ratings.py": PRE_INGESTION,
    "scripts/eodhd/v2/transforms/transform_dividends.py": PRE_INGESTION,
    "scripts/assert_feed_health.py": PRE_INGESTION,
    "scripts/asic/transforms/transform_short.py": PRE_INGESTION,
    "compute/engine/weekly_compute.py": PRE_INGESTION,
    "compute/engine/monthly_compute.py": PRE_INGESTION,

    # Downstream consumers. Both READ canonical outputs and write only their
    # own artifacts. They are the concrete reason the lease must be held
    # through the suffix: reading screener.universe while a later run's
    # provisional rebuild is in flight would observe un-attributed state.
    "compute/engine/heatmap_compute.py": POST_PUBLICATION,
    "compute/engine/sector_benchmarks.py": POST_PUBLICATION,

    # Writes screener.universe, non-governed columns only, inside the
    # lease and after finalisation. See SUFFIX_WRITE_REASONS.
    "compute/engine/pros_cons.py": POST_PUBLICATION_WRITER,

    # ── Launched by cron, not by a pipeline. See launch_authority. ──────────
    # Reads screener.universe to pick the monthly five. A live-universe
    # consumer, so it belongs in a suffix under the lease or must become
    # run-pinned; an independent Sunday cron is outside the contract, which
    # launch_authority reports separately from this classification.
    "compute/engine/top5_strategy.py": POST_PUBLICATION,
    # Writes market.asx_announcements, a canonical INPUT.
    "scripts/asx/download_announcements.py": PRE_INGESTION,
    # Writes market.daily_prices, a canonical OUTPUT. Illegal for ingestion —
    # see ACCEPTED, where the open question is recorded.
    "scripts/eodhd/v2/backfill_yfinance_prices.py": PRE_INGESTION,
}

#: Known, accepted boundary violations — debts, not dispensations.
#:
#: An entry here keeps the test green for the state we have already decided
#: about, so that a NEW violation still breaks the build. It does not make the
#: violation acceptable, and a stale entry — one whose step no longer violates
#: — fails just as loudly as an undeclared one, because an allowlist nobody
#: prunes is an allowlist nobody reads.
ACCEPTED: dict[str, str] = {
    "scripts/eodhd/v2/backfill_yfinance_prices.py":
        "Writes market.daily_prices — a canonical OUTPUT, written by the "
        "plan stage transform_prices — from an independent 09:00 UTC weekday "
        "cron, fifteen minutes after daily_pipeline starts. No classification "
        "is legal for it: PRE_INGESTION may not write an output, and "
        "POST_PUBLICATION may not write a dependency table at all. 'Three "
        "days is outside the yearly fingerprint's historical scope' is NOT "
        "sufficient safety, because recent rows are exactly what daily and "
        "technical compute consume. Two open questions this module does not "
        "answer: whether it belongs in the daily wrapper's prefix inside the "
        "lease, and whether market.daily_prices having two legitimate writers "
        "means the output/input split needs revisiting. Raised 25 Sep 2026 by "
        "the first run of the launch-authority classifier.",
}


def classification(step: Step) -> str | None:
    if step.key in {p.relative_to(BACKEND).as_posix()
                    for p in plan_scripts().values()}:
        return CANONICAL_DRIVER
    return CLASSIFICATIONS.get(step.key)


# ── The verdict ──────────────────────────────────────────────────────────────

def violations(include_accepted: bool = False) -> list[str]:
    """Every way the declared boundary disagrees with the derived one.

    By default the entries in ACCEPTED are withheld, so this returns only what
    is NEW. Pass include_accepted to see the full picture.
    """
    found = [v for v in _all_violations()
             if include_accepted or _key_of(v) not in ACCEPTED]
    # A stale exemption is its own failure. If the step named in ACCEPTED has
    # stopped violating, the entry is describing a world that no longer exists
    # and the next reader will trust it anyway.
    # A stale exemption is its own failure — but only where the unit is
    # actually visible. backfill_yfinance_prices exists in the runtime crontab
    # and not in the checked-in generator, so off-server this module cannot
    # see it at all. "I cannot see this unit here" is not "this unit no longer
    # violates", and the first draft reported the second when it meant the
    # first.
    visible = all_units()
    still = {_key_of(v) for v in _all_violations()}
    for key in ACCEPTED:
        if key in visible and key not in still:
            found.append(
                f"STALE EXEMPTION  {key} is listed in ACCEPTED but no longer "
                f"violates the boundary. Remove the entry.")
    return found


def _key_of(violation: str) -> str:
    """The script path a violation line names."""
    for token in violation.split():
        if token.endswith(".py"):
            return token
    return ""


def check_unit(key: str, script: Path) -> list[str]:
    """The directional rules, for one launchable unit.

    Factored out so cron-launched scripts go through exactly these rules
    rather than a parallel copy in `launch_authority`. Two copies of "what may
    a pre-ingestion step write" is two answers that drift, which is the defect
    this module exists to prevent — it does not stop being that when both
    copies are ours.
    """
    inputs, outputs = canonical_tables()
    hits = {t: d for t, d in tables_touched(script).items()
            if t in inputs | outputs}
    if not hits:
        return []

    plan_keys = {p.relative_to(BACKEND).as_posix()
                 for p in plan_scripts().values()}
    kind = CANONICAL_DRIVER if key in plan_keys else CLASSIFICATIONS.get(key)
    if kind is None:
        return [f"UNCLASSIFIED  {key} touches canonical dependency tables "
                f"{sorted(hits)} and has no classification"]

    written = {t for t, d in hits.items() if "w" in d}
    found: list[str] = []

    if kind == PRE_INGESTION:
        owned = written & outputs
        if owned:
            found.append(
                f"{PRE_INGESTION}  {key} writes canonical OUTPUTS "
                f"{sorted(owned)}, which the driver owns")

    elif kind == POST_PUBLICATION:
        if written:
            found.append(
                f"{POST_PUBLICATION}  {key} writes canonical dependency "
                f"tables {sorted(written)}; a post-publication step may read "
                f"them but never mutate them. If the write is intended, "
                f"classify it {POST_PUBLICATION_WRITER} and state why — it "
                f"will then run inside the lease and its non-governed claim "
                f"will be checked.")

    elif kind == POST_PUBLICATION_WRITER:
        if key not in SUFFIX_WRITE_REASONS:
            found.append(
                f"{POST_PUBLICATION_WRITER}  {key} writes a shared canonical "
                f"table with no stated reason")
        governed = governed_columns()
        for table in sorted(written):
            overlap = columns_written(script, table) & governed
            if overlap:
                found.append(
                    f"{POST_PUBLICATION_WRITER}  {key} writes GOVERNED "
                    f"columns {sorted(overlap)} of {table}. A suffix writer "
                    f"may share the table; it may not touch a value the "
                    f"canonical run is accountable for.")
    return found


def _all_violations() -> list[str]:
    found: list[str] = []
    for key, script in sorted(all_units().items()):
        found.extend(check_unit(key, script))
    return found


def report() -> str:
    inputs, outputs = canonical_tables()
    lines = [
        f"canonical outputs ({len(outputs)}): {', '.join(sorted(outputs))}",
        f"canonical inputs  ({len(inputs)}): {', '.join(sorted(inputs))}",
        "",
    ]
    seen: set[str] = set()
    for step in all_steps():
        if step.key in seen:
            continue
        seen.add(step.key)
        hits = {t for t in tables_touched(step.script) if t in dependency_tables()}
        if not hits:
            continue
        lines.append(f"  {classification(step) or 'UNCLASSIFIED':17} "
                     f"{step.key}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    print(report())
    if ACCEPTED:
        print("\naccepted (known debts, still violations):")
        for key, reason in ACCEPTED.items():
            print(f"  {key}\n    {reason[:140]}...")
    bad = violations()
    print()
    for line in bad:
        print(" ", line)
    print(f"{len(bad)} new violation(s)")
    sys.exit(1 if bad else 0)
