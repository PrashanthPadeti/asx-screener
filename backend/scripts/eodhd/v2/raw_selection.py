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


def all_payloads_oldest_first(paths) -> list:
    """EVERY payload, oldest first — never one file per code.

    Picking a single payload per code is wrong in BOTH directions, and we
    made both mistakes in one day:

      oldest  drops every split recorded after a code's first download
              (EVR kept its 2008 and 2017 consolidations and lost the
              1-for-10 of 2026-09-08)
      newest  drops the history the newest response omits — EODHD's splits
              endpoint does NOT reliably return the full series even with
              `from=2000-01-01`. EVR's 2026-10-04 payload contains ONLY the
              September consolidation, so preferring it lost 2008 and 2017.
              Across the exchange that cost 104 split records.

    A payload is therefore evidence of the splits it contains, and evidence
    of nothing about the ones it omits. Load them all and let
    `ON CONFLICT (asx_code, date) DO UPDATE` reconcile: every date from every
    file is kept, and where two files describe the same date the later file
    wins because it is applied last.
    """
    return sorted(paths, key=lambda p: p.name)


def latest_files_by_code(paths) -> list:
    """Deprecated: one payload per code, newest.

    Retained only because selecting a single payload is still correct for
    datasets whose provider returns a complete series every time. It is NOT
    correct for splits — see all_payloads_oldest_first.
    """
    seen: dict[str, Path] = {}
    for f in sorted(paths, key=lambda p: p.name, reverse=True):
        code = code_of(f)
        if code not in seen:
            seen[code] = f
    return sorted(seen.values(), key=lambda p: p.name)
