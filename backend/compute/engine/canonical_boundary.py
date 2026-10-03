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

#: Schemas whose tables can carry state into a governed value.
#:
#: CLASSIFICATION ONLY. Extraction does not consult this and must not: a
#: hand-maintained enumeration decides what is *visible*, and anything it
#: omits is invisible rather than irrelevant. Until 1 Oct 2026 this tuple WAS
#: the extraction pattern, so `users` (201 SQL references), `meta`, `support`
#: and `strategy` could not be seen at all -- `tables_touched(top5_strategy)`
#: returned no writes for a job that INSERTs, UPDATEs and DELETEs
#: `strategy.monthly_picks`.
#:
#: The rule that replaced it: extraction discovers every schema-qualified
#: relation; classification decides which ones matter.
CANONICAL_SCHEMAS = ("financials", "market", "staging_au", "screener")

#: Kept as an alias because callers and tests refer to it, but it no longer
#: governs what can be seen.
SCHEMAS = CANONICAL_SCHEMAS

_IDENT = r"[A-Za-z_][A-Za-z0-9_$]*"
#: Any schema-qualified relation, whatever the schema. Qualification is the
#: discriminator that keeps CTEs, aliases and derived tables out: those are
#: referenced by bare name, so they cannot match.
_QUALIFIED = rf"{_IDENT}\.{_IDENT}"

#: A relation reference the extractor cannot resolve to a name: an f-string
#: placeholder, a %-format slot, or a psycopg2 parameter in table position.
#: These must become UNRESOLVED and never silently "no tables" -- a producer
#: whose target is computed at runtime is the one most worth knowing about.
_PLACEHOLDER = r"\{[^}]*\}|%\([^)]*\)s|%s"

#: Verb -> direction. Order matters inside the alternation: `DELETE FROM` and
#: `INSERT INTO` must be tried before the bare `FROM`/`INTO` they contain, or a
#: deletion is recorded as a read and the step looks harmless.
_VERBS = [
    ("INSERT INTO", "w"), ("DELETE FROM", "w"), ("TRUNCATE TABLE", "w"),
    ("TRUNCATE", "w"), ("MERGE INTO", "w"), ("UPDATE", "w"), ("COPY", "w"),
    ("FROM", "r"), ("JOIN", "r"), ("USING", "r"),
]
_VERB_ALT = "|".join(v.replace(" ", r"\s+") for v, _ in _VERBS)

#: The relation that follows a verb: qualified, or a placeholder, or a bare
#: name. All three are captured; `_classify_reference` decides what each is,
#: so an unreadable reference is reported rather than dropped.
_PATTERN = re.compile(
    rf"\b({_VERB_ALT})\s+(?:ONLY\s+)?({_QUALIFIED}|{_PLACEHOLDER}|{_IDENT})",
    re.IGNORECASE)
_DIRECTION = {v.lower(): d for v, d in _VERBS}

#: Names introduced by WITH ... AS, which are referenced like relations and
#: are not one. Collected per-statement and excluded explicitly rather than
#: relied upon to be unqualified.
_CTE = re.compile(rf"\b(?:WITH|,)\s+({_IDENT})\s+AS\s*(?:MATERIALIZED\s*)?\(",
                  re.IGNORECASE)


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
        # By LINE RANGE, not by string replace.
        #
        # ast.get_docstring returns the PARSED value, so a docstring
        # containing an escape -- `\n`, `\t`, or a line continuation -- never
        # matches its own source text and `src.replace(doc, "")` silently
        # removes nothing. Ten docstrings in this tree are affected, including
        # weekly_pipeline and monthly_pipeline.
        #
        # incremental_daily.py is what exposed it: its docstring says
        # "- Does NOT update screener.universe", that line survived stripping,
        # and the extractor recorded a WRITE to screener.universe from a
        # sentence asserting the opposite. It was quarantined as a latent
        # canonical writer on that basis.
        drop: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                end = first.end_lineno or first.lineno
                drop.update(range(first.lineno, end + 1))
        if drop:
            src = "\n".join(line for n, line in enumerate(src.splitlines(), 1)
                            if n not in drop)

    # `--` matters as much as `#`: these files carry SQL in triple-quoted
    # strings, and a commented-out UPDATE inside one is not a write.
    return "\n".join(line for line in src.splitlines()
                     if not line.strip().startswith(("#", "--")))


# The optional alias is not cosmetic. `UPDATE screener.universe u SET ...` is
# the shape short_positions uses, and a pattern demanding SET immediately after
# the table reported NO columns for it — silently clearing an aliased writer of
# exactly the check that exists to police it. Found when the scheduler trace
# said that job writes screener.universe while this said it writes nothing.
_SET_LIST = re.compile(
    rf"\bUPDATE\s+({_QUALIFIED})(?:\s+(?!SET\b)(?:AS\s+)?\w+)?\s+SET\s+"
    rf"(.*?)(?=\bFROM\b|\bWHERE\b|\bRETURNING\b|;|\"\"\")",
    re.IGNORECASE | re.DOTALL)
_INSERT_LIST = re.compile(
    rf"\bINSERT\s+INTO\s+({_QUALIFIED})\s*\(([^)]*)\)",
    re.IGNORECASE | re.DOTALL)
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


def sql_text(path: Path) -> str:
    """The SQL a file contains, with Python syntax removed.

    Scanning raw source cannot work once extraction stops enumerating
    schemas: `from compute.engine.run_plans import PLANS` matches
    `FROM <qualified>` perfectly. The old allow-list was concealing that --
    `compute` was not a known schema, so the false positive never appeared.

    For a .py file the SQL lives in string literals, so those are what is
    scanned. Docstrings are excluded for the reason _executable_source
    exists: prose about a table is not a reference to it. For anything else
    the whole file is SQL-bearing text with its comment lines removed.
    """
    if path.suffix != ".py":
        return _executable_source(path)

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return _executable_source(path)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)

    chunks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                chunks.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            # An f-string: keep the literal parts and mark each interpolation
            # so a computed table name survives as a placeholder rather than
            # vanishing into the gap between two literal fragments.
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("{}")
            chunks.append("".join(parts))

    text = "\n".join(chunks)

    # A Python import written INSIDE a string literal. budget_audit.py builds
    # a subprocess command containing
    #     "import asyncio; from app.workers.announcement_worker import ..."
    # and `FROM app.workers` matched it perfectly once extraction stopped
    # enumerating schemas. The discriminator is the `import` that follows:
    # `from X.Y import Z` is not a shape SQL has.
    text = re.sub(rf"\bfrom\s+{_IDENT}(?:\.{_IDENT})*\s+import\b", " ", text)

    # SQL comments inside the strings are not references either.
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("--"))


def _cte_names(text: str) -> set[str]:
    return {n.lower() for n in _CTE.findall(text)}


def relations(path: Path) -> tuple[dict[str, set[str]], list[str]]:
    """({relation: {'r','w'}}, unresolved) for one file.

    Schema-agnostic: any `schema.table` is discoverable without being
    enumerated anywhere. Whether a relation MATTERS is a classification
    question answered elsewhere -- extraction that decides relevance is
    extraction that can hide things by omission.

    The second element is the honest part. A reference the extractor cannot
    resolve to a name becomes UNRESOLVED and is returned, never silently
    dropped: a producer whose target is computed at runtime is precisely the
    one worth knowing about.
    """
    text = sql_text(path)
    ctes = _cte_names(text)
    found: dict[str, set[str]] = {}
    unresolved: list[str] = []

    for verb, ref in _PATTERN.findall(text):
        direction = _DIRECTION[" ".join(verb.split()).lower()]
        token = ref.strip()

        if re.fullmatch(_PLACEHOLDER, token):
            unresolved.append(f"{' '.join(verb.split()).upper()} {token}")
            continue
        if "." not in token:
            # A bare name: a CTE, an alias, a derived table, or a temp
            # relation. Not a physical schema-qualified relation, and not
            # reported as one.
            continue
        if token.split(".", 1)[0].lower() in ctes:
            continue
        found.setdefault(token.lower(), set()).add(direction)

    return found, sorted(set(unresolved))


def tables_touched(path: Path) -> dict[str, set[str]]:
    """{relation: {'r', 'w'}} for one script.

    The historical name and shape, kept because callers depend on it. Use
    `relations()` when the unresolved references matter -- and they usually
    do, since this signature cannot express them.
    """
    return relations(path)[0]


def unresolved_relations(path: Path) -> list[str]:
    """Relation references this file computes at runtime."""
    return relations(path)[1]


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


#: Files that write a canonical OUTPUT but are launched by nothing — no cron
#: entry, no pipeline step, no scheduler registration. They can only run if a
#: person runs them.
#:
#: "Launched by nothing" is not the same as "cannot write". The launch
#: authorities are enumerated; the tree is not, and a script sitting in it with
#: an INSERT into a canonical output is one `python scripts/...` away from
#: being a second publication authority. Rule 5 says a canonical output has one
#: publication authority, and that claim is about the table, not about the
#: schedule.
#:
#: Listed with a reason rather than deleted, because deletion is the user's
#: call and an undeclared latent writer is worse than a declared one.
QUARANTINED_WRITERS: dict[str, str] = {
    # incremental_daily.py was quarantined here as a latent canonical writer.
    # It never was one. Its module docstring says
    #     - Does NOT update screener.universe
    # and that line survived docstring stripping because the docstring also
    # contains a line continuation, so `src.replace(doc, "")` matched nothing.
    # The extractor then read the sentence as `UPDATE screener.universe` and
    # recorded a write from prose asserting the opposite. Removed 1 Oct 2026
    # once extraction stopped reading docstrings; the file dispatches
    # subprocesses and issues no SQL at all.
    "compute/engine/dilution_metrics.py":
        "writes screener.universe (shares_change_1y, shares_dilution_3y and "
        "two others, none governed) and is launched by NOTHING: no cron "
        "entry, no pipeline step, no scheduler registration. Found 27 Sep "
        "2026 by the tree-wide writer scan, which is the first instrument "
        "that looked past the launch authorities. OPEN: it is either dead and "
        "should be deleted, or it is run by hand and belongs in the suffix "
        "under the lease like the other auxiliary writers. This module does "
        "not decide that.",
    "scripts/load_eodhd_prices.py": "pre-v2 loader",
    "scripts/load_fmp_prices.py": "pre-v2 loader, FMP feed no longer used",
    "scripts/load_prices.py": "pre-v2 loader",
    "scripts/update_prices.py": "pre-v2 incremental updater",
    "scripts/update_prices_eodhd.py": "pre-v2 incremental updater",
    "scripts/update_prices_fmp.py": "pre-v2 incremental updater, FMP feed",
    "scripts/eodhd/load_prices.py": "pre-v2 loader, superseded by "
                                    "eodhd/v2/transforms/transform_prices.py",
}

#: Modules that perform a plan stage's writes but are not themselves launched.
#:
#: universe_writer is imported BY composite_score — it is the canonical
#: writer's implementation, not a second authority. Counting it as one would
#: count the same publication twice, under the name of the file that happens
#: to hold the SQL.
CANONICAL_LIBRARIES: dict[str, str] = {
    "compute/engine/universe_writer.py":
        "implements the canonical commit for composite_score; imported, "
        "never launched",
}

#: Directories that are not application code: virtualenvs, caches, the
#: discovery worktree. Scanning them would report a dependency's own SQL.
_NOT_OURS = ("__pycache__", ".git", "node_modules", "site-packages",
             ".venv", "asx-venv", "tests")


def output_writers() -> dict[str, set[str]]:
    """{canonical output: every file in the tree that writes it}.

    Tree-wide, deliberately. `all_units()` answers "what does each LAUNCHED
    thing touch"; this answers "what could write this table at all", which is
    the question Rule 5 actually asks.
    """
    _inputs, outputs = canonical_tables()
    found: dict[str, set[str]] = {t: set() for t in outputs}
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if any(part in rel for part in _NOT_OURS):
            continue
        for table, directions in tables_touched(path).items():
            if table in found and "w" in directions:
                found[table].add(rel)
    return found


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
    "compute/engine/asx_indices.py":
        "Writes shared canonical table screener.universe; non-governed "
        "columns (is_asx20/50/100/200/300 index membership flags). Launched "
        "by the in-process scheduler at 17:50 AEST, not by a pipeline, so it "
        "currently holds uncoordinated write authority over the live table. "
        "Decided 27 Sep 2026: stays OUT of the canonical plan — it determines "
        "none of the 72 governed values and its failure must not gate "
        "finalisation — and is serialized by the same table-level lease. It "
        "may keep its own schedule; it may not keep uncoordinated authority.",
    "compute/engine/short_positions.py":
        "Writes shared canonical table screener.universe; non-governed "
        "columns (short_pct, short_interest_chg_1w). Launched by the "
        "in-process scheduler at 20:05 AEST. Same decision and same reasoning "
        "as asx_indices: out of the plan, inside the lease. Its aliased "
        "UPDATE is also what exposed the column extractor's blind spot, since "
        "the call trace said it writes the universe while the extractor said "
        "it writes nothing.",
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
    "compute/engine/asx_indices.py": POST_PUBLICATION_WRITER,
    "compute/engine/short_positions.py": POST_PUBLICATION_WRITER,

    # ── Launched by cron, not by a pipeline. See launch_authority. ──────────
    # Reads screener.universe to pick the monthly five. A live-universe
    # consumer, so it belongs in a suffix under the lease or must become
    # run-pinned; an independent Sunday cron is outside the contract, which
    # launch_authority reports separately from this classification.
    "compute/engine/top5_strategy.py": POST_PUBLICATION,
    # Writes market.asx_announcements, a canonical INPUT.
    "scripts/asx/download_announcements.py": PRE_INGESTION,
}

#: Known, accepted boundary violations — debts, not dispensations.
#:
#: An entry here keeps the test green for the state we have already decided
#: about, so that a NEW violation still breaks the build. It does not make the
#: violation acceptable, and a stale entry — one whose step no longer violates
#: — fails just as loudly as an undeclared one, because an allowlist nobody
#: prunes is an allowlist nobody reads.
#: Empty. backfill_yfinance_prices was the only entry, and the question it
#: recorded — where a second writer of market.daily_prices belongs — was
#: answered by deleting the writer rather than by relocating it. Its coverage
#: was eight instruments carrying prices 35-49 days stale, and the
#: stale-exemption guard is what forced the entry out rather than letting it
#: become a permanent excuse.
ACCEPTED: dict[str, str] = {}


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
    # actually visible. A unit can exist in the runtime crontab and not in the
    # checked-in generator — backfill_yfinance_prices did, before it was
    # deleted — so off-server this module cannot see it at all. "I cannot see
    # this unit here" is not "this unit no longer violates", and the first
    # draft reported the second when it meant the first.
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
    found.extend(_publication_authority_violations())
    return found


def _publication_authority_violations() -> list[str]:
    """Rule 5: a canonical output table has ONE publication authority."""
    plan_keys = {p.relative_to(BACKEND).as_posix()
                 for p in plan_scripts().values()}
    found: list[str] = []
    for key, kind in sorted(CLASSIFICATIONS.items()):
        if kind == POST_PUBLICATION_WRITER and key not in SUFFIX_WRITE_REASONS:
            found.append(
                f"{POST_PUBLICATION_WRITER}  {key} shares a canonical table "
                f"with no stated reason. check_unit only sees LAUNCHED units, "
                f"and a scheduler job is not one, so the requirement is "
                f"enforced here too.")

    for table, writers in sorted(output_writers().items()):
        permitted = {k for k, v in CLASSIFICATIONS.items()
                     if v == POST_PUBLICATION_WRITER}
        undeclared = sorted(writers - plan_keys - set(QUARANTINED_WRITERS)
                            - set(CANONICAL_LIBRARIES) - permitted)
        if undeclared:
            found.append(
                f"SECOND PUBLICATION AUTHORITY  {table} is written by "
                f"{undeclared}, which are neither plan stages nor declared "
                f"quarantined. A canonical output has one publication "
                f"authority.")
    # A quarantine entry for a file that no longer writes an output is a
    # comment nobody will delete, and it makes the list look longer than the
    # problem is.
    live = {w for writers in output_writers().values() for w in writers}
    live |= set(CANONICAL_LIBRARIES)
    for path in sorted(set(QUARANTINED_WRITERS) - live):
        found.append(
            f"STALE QUARANTINE  {path} is listed as a latent writer but no "
            f"longer writes any canonical output. Remove the entry.")
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


def freshness_relevant_tables() -> set[str]:
    """Tables where staleness is a customer-visible fault.

    The intersection of two facts already derivable from the source: the API
    READS the table to serve a request, and a scheduled job WRITES it. Both
    halves matter. A table nothing serves cannot show a customer a stale
    number; a table nothing produces cannot go stale because nothing was
    keeping it fresh.

    Derived rather than listed, because a hand-written list is exactly how
    market.daily_prices came to be unwatched while a four-day hole opened in
    it and the freshness check reported FRESH for a week.
    """
    def scan(paths) -> tuple[set[str], set[str]]:
        reads: set[str] = set()
        writes: set[str] = set()
        for path in paths:
            try:
                touched, _ = relations(path)
            except Exception:                                   # noqa: BLE001
                continue
            for table, directions in touched.items():
                if "." not in table:
                    continue
                if "r" in directions:
                    reads.add(table)
                if "w" in directions:
                    writes.add(table)
        return reads, writes

    api_reads, _ = scan(sorted((BACKEND / "app/api/v1/routes").glob("*.py")))
    _, produced = scan(
        list((BACKEND / "app/workers").glob("*.py"))
        + list((BACKEND / "scripts").rglob("*.py"))
        + list((BACKEND / "compute/engine").glob("*.py")))
    return api_reads & produced
