"""
Every mechanism that can launch code in production, enumerated
==============================================================
`canonical_boundary` classifies the steps the three pipelines run. That made
it an authority over the pipelines and left it silent about everything else —
and "everything else" includes cron entries that write canonical tables on
their own schedule, coordinated by nothing.

    The classifier is only an implementation authority once it covers every
    execution authority capable of touching the canonical dependency graph.

Two artifacts, one job each
---------------------------
    setup_cron.sh      DESIRED state. Checked in, reviewable, what code
                       review can reason about.
    crontab -l         OBSERVED state. What can actually mutate production.

Neither is truth alone, and neither is rewritten to match the other. They must
AGREE on every canonical-relevant entry; where they do not, that is a finding
to resolve explicitly rather than a race to pick a winner. The distinction
matters right now: the daily and weekly pipelines are deliberately disabled at
runtime while the generator still declares them enabled, so the generator is
currently unsafe to rerun as though it described the system.

Comparison is semantic — executable, cadence, enabled state — not textual.
Inline reasons and whitespace are legitimate differences; a different cadence
is not.

Independent launch
------------------
A step can be correctly classified and still be wrong, because classification
answers "what may this touch?" and scheduling answers "while what else is
running?". A canonical-relevant step launched directly by cron is, by
construction, outside the canonical execution lease: nothing sequences it
against a run that may be computing from the same tables. That is reported
separately from the table-direction rules, because the remedy is different —
it moves into a wrapper, or becomes run-pinned, rather than being
reclassified.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compute.engine import canonical_boundary as cb  # noqa: E402

REPO = cb.BACKEND.parent
GENERATOR = cb.BACKEND / "scripts" / "eodhd" / "v2" / "jobs" / "setup_cron.sh"

#: Targets that ARE wrappers. A pipeline launched by cron is the orchestration
#: boundary itself, not a step running beside it, so it is exempt from the
#: independent-launch rule — its own steps are classified by
#: canonical_boundary.
WRAPPERS = {f"backend/scripts/eodhd/v2/jobs/{p}" for p in cb.PIPELINES}

_CADENCE = r"(?:[-\d*/,]+\s+){4}[-\d*/,]+"
_CRON_LINE = re.compile(rf"^(#?)\s*.*?({_CADENCE})\s+(.*)$")
_ASSIGN = re.compile(r'^(\w+)="(.*)"\s*$', re.MULTILINE)


@dataclass(frozen=True)
class Scheduled:
    """One scheduled command, normalised for comparison."""

    source: str
    cadence: str
    target: str          # repo-relative script path, or "" if none found
    enabled: bool
    raw: str

    @property
    def identity(self) -> tuple[str, str, bool]:
        """What must match between desired and observed. Deliberately not the
        raw line: a disabled entry carries an inline reason, and that is a
        legitimate difference rather than drift."""
        return (self.target, " ".join(self.cadence.split()), self.enabled)


def _target_of(command: str) -> str:
    """The script a cron command runs, repo-relative."""
    module = re.search(r"-m\s+([\w.]+)", command)
    if module:
        return "backend/" + module.group(1).replace(".", "/") + ".py"
    script = re.search(r"([\w./-]+\.(?:py|sh))", command.replace("/opt/asx-screener/", ""))
    if not script:
        return ""
    found = script.group(1).lstrip("./")
    return found


def _parse(line: str, source: str) -> Scheduled | None:
    matched = _CRON_LINE.match(line.strip())
    if not matched:
        return None
    commented, cadence, command = matched.groups()
    return Scheduled(source=source, cadence=cadence, target=_target_of(command),
                     enabled=not commented, raw=line.strip())


def desired() -> list[Scheduled]:
    """Scheduled commands the checked-in generator declares.

    Read from its `*_CMD="..."` assignments with the shell variables it also
    defines expanded, so the comparison is against the line the generator
    would actually install rather than against a template.
    """
    text = GENERATOR.read_text(encoding="utf-8")
    variables = dict(_ASSIGN.findall(text))
    found: list[Scheduled] = []
    for name, value in variables.items():
        if not name.endswith("_CMD"):
            continue
        for _ in range(4):                       # nested expansions
            value = re.sub(r"\$\{(\w+)\}",
                           lambda m: variables.get(m.group(1), m.group(0)), value)
        parsed = _parse(value, "setup_cron.sh")
        if parsed:
            found.append(parsed)
    return found


def observed(crontab: str) -> list[Scheduled]:
    """Scheduled commands actually installed. Pass the output of `crontab -l`."""
    found = []
    for line in crontab.splitlines():
        if not line.strip():
            continue
        parsed = _parse(line, "crontab")
        if parsed and parsed.target:
            found.append(parsed)
    return found


def read_crontab() -> str | None:
    """The installed crontab, or None where there is no crontab to read."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True,
                                text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


# ── The rules ────────────────────────────────────────────────────────────────

def touches_canonical(target: str) -> dict[str, set[str]]:
    """Which canonical dependency tables a scheduled target touches."""
    path = REPO / target
    if not path.exists() or path.suffix != ".py":
        return {}
    deps = cb.dependency_tables()
    return {t: d for t, d in cb.tables_touched(path).items() if t in deps}


def register_observed(crontab: str) -> dict[str, Path]:
    """Teach `canonical_boundary` about units only the runtime knows.

    The checked-in generator declares four commands; the installed crontab has
    seven. Without this, three canonical-relevant scripts are invisible to the
    boundary everywhere except here — and an exemption for one of them would
    be reported as stale rather than as an open question.
    """
    added: dict[str, Path] = {}
    for entry in observed(crontab):
        key = _classification_key(entry.target)
        path = REPO / entry.target
        if path.exists() and path.suffix == ".py" and touches_canonical(entry.target):
            added[key] = path
    cb.EXTRA_UNITS.update(added)
    return added


def reconciliation(crontab: str) -> list[str]:
    """Where desired and observed disagree on a canonical-relevant entry."""
    want = {s.identity: s for s in desired()}
    have = {s.identity: s for s in observed(crontab)}
    found: list[str] = []

    want_targets = {s.target for s in desired()}
    have_targets = {s.target for s in observed(crontab)}

    for target in sorted(have_targets - want_targets):
        if touches_canonical(target):
            found.append(
                f"UNDECLARED  {target} is installed and touches canonical "
                f"tables {sorted(touches_canonical(target))}, but the "
                f"generator does not declare it. Production runs something "
                f"code review cannot see.")
    for target in sorted(want_targets - have_targets):
        found.append(
            f"NOT INSTALLED  the generator declares {target}, which is absent "
            f"from the installed crontab")

    for target in sorted(want_targets & have_targets):
        w = next(s for s in desired() if s.target == target)
        h = next(s for s in observed(crontab) if s.target == target)
        if w.identity == h.identity:
            continue
        if w.enabled != h.enabled:
            found.append(
                f"ENABLED-STATE DRIFT  {target}: generator declares "
                f"{'enabled' if w.enabled else 'disabled'}, runtime is "
                f"{'enabled' if h.enabled else 'disabled'}. Rerunning the "
                f"generator would not reproduce the running system.")
        if " ".join(w.cadence.split()) != " ".join(h.cadence.split()):
            found.append(
                f"CADENCE DRIFT  {target}: generator '{w.cadence}', runtime "
                f"'{h.cadence}'")
    return found


def independent_launches(crontab: str | None = None) -> list[str]:
    """Canonical-relevant commands cron launches outside any wrapper.

    Evaluated against DESIRED state when no crontab is supplied, so the rule
    holds in any environment; the server-side test passes the observed one as
    well, because a command only present at runtime is the more dangerous of
    the two.
    """
    entries = desired() if crontab is None else desired() + observed(crontab)
    found: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry.enabled or entry.target in WRAPPERS or entry.target in seen:
            continue
        hits = touches_canonical(entry.target)
        if not hits:
            continue
        seen.add(entry.target)

        key = _classification_key(entry.target)
        kind = cb.CLASSIFICATIONS.get(key)
        written = {t for t, d in hits.items() if "w" in d}
        detail = (f"writes {sorted(written)}" if written
                  else f"reads {sorted(hits)}")
        found.append(
            f"INDEPENDENT LAUNCH  {entry.target} ({entry.cadence}) {detail} "
            f"with no wrapper and therefore no canonical execution lease"
            + (f"; classified {kind}" if kind else "; unclassified"))

        # The directional rules too, through canonical_boundary's own
        # checker. A cron-launched script is a launchable unit like any
        # other; the only thing special about it is that nothing sequences it.
        for problem in cb.check_unit(key, REPO / entry.target):
            if key not in cb.ACCEPTED:
                found.append(problem)
    return found


def _classification_key(target: str) -> str:
    """Repo-relative -> the backend-relative key CLASSIFICATIONS uses."""
    return target[len("backend/"):] if target.startswith("backend/") else target


def report(crontab: str | None = None) -> str:
    lines = ["desired (setup_cron.sh):"]
    for entry in sorted(desired(), key=lambda s: s.target):
        hits = touches_canonical(entry.target)
        lines.append(f"  {entry.cadence:14} {entry.target:52} "
                     f"{'canonical' if hits else '-'}")
    if crontab is not None:
        lines.append("\nobserved (crontab -l):")
        for entry in sorted(observed(crontab), key=lambda s: s.target):
            hits = touches_canonical(entry.target)
            lines.append(f"  {'ON ' if entry.enabled else 'OFF'} "
                         f"{entry.cadence:14} {entry.target:52} "
                         f"{'canonical' if hits else '-'}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    live = read_crontab()
    print(report(live))
    problems = independent_launches(live)
    if live is not None:
        problems = reconciliation(live) + problems
    else:
        print("\n(no crontab readable here — reconciliation needs the server)")
    print()
    for line in problems:
        print(" ", line)
    print(f"\n{len(problems)} finding(s)")
    sys.exit(1 if problems else 0)
