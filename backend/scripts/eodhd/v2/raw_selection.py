"""
Choosing which raw payload to load when a code has several
==========================================================
Raw payloads are written as `CODE.AU_YYYY-MM-DD.json.gz`, one per fetch, and
each file contains the WHOLE history as of that date. So when a code has
several files, the newest supersedes the rest — loading an older one silently
discards everything recorded since.

Kept here, free of database and configuration imports, so the rule can be
tested directly. The bug it exists to prevent was invisible for six months
precisely because it lived inline in a loader nothing could exercise.

What happened (26 Oct 2026): the splits loader deduplicated with

    for f in sorted(paths):          # ascending — OLDEST first
        if code not in seen:
            seen[code] = f           # keeps the first it sees

and the comment above it said "one (latest) file per code". EVR had
`EVR.AU_2026-04-28.json.gz` (its 2008 and 2017 consolidations) and
`EVR.AU_2026-10-04.json.gz` (the 1-for-10 of 2026-09-08). The ascending sort
loaded April and dropped September. Every return window spanning that
consolidation was therefore computed across a 10x price step that
market.splits had no record of.
"""

from pathlib import Path


def code_of(path: Path) -> str:
    """`EVR.AU_2026-10-04.json.gz` -> `EVR`."""
    return path.name.split("_")[0].replace(".AU", "")


def latest_files_by_code(paths) -> list:
    """One payload per code: the newest, by the date in its filename.

    Returned in stable name order so a run's progress is readable and two
    runs over the same directory process in the same sequence.
    """
    seen: dict[str, Path] = {}
    # reverse=True puts the newest filename first, so the `not in seen`
    # guard keeps it. Ascending would keep the oldest — see the module
    # docstring; that inversion cost six months of split history.
    for f in sorted(paths, key=lambda p: p.name, reverse=True):
        code = code_of(f)
        if code not in seen:
            seen[code] = f
    return sorted(seen.values(), key=lambda p: p.name)
