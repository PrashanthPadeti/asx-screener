"""
When a code has several raw payloads, load the newest
=====================================================
Raw payloads are `CODE.AU_YYYY-MM-DD.json.gz`, one per fetch, each holding
the WHOLE history as of that date. Loading an older one silently discards
everything recorded since.

The splits loader deduplicated with an ASCENDING sort and `if code not in
seen`, which keeps the FIRST file seen — the oldest. The comment above it
said "one (latest) file per code". For six months the loader read April's
payload and discarded October's.

What that cost: EVR's `2026-04-28` file holds its 2008 and 2017
consolidations; its `2026-10-04` file holds the 1-for-10 of 2026-09-08. Only
April was ever loaded, so `market.splits` had no record of the
consolidation — and because every return on the site is computed from
unadjusted close, every return window spanning 8 September showed a ~-90%
move that never happened.

Pure, and tested on filenames alone, because the defect was invisible for
six months precisely while it sat inline in a loader nothing could exercise.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts.eodhd.v2.raw_selection import (                   # noqa: E402
    all_payloads_oldest_first, code_of, latest_files_by_code,
)


def P(*names) -> list:
    return [Path(n) for n in names]


def test_the_newest_payload_wins():
    """The exact shape of the defect: a later fetch whose name sorts
    LOWER-first under an ascending sort."""
    picked = latest_files_by_code(P(
        "EVR.AU_2026-04-28.json.gz",
        "EVR.AU_2026-10-04.json.gz",
    ))
    assert [p.name for p in picked] == ["EVR.AU_2026-10-04.json.gz"], (
        "the older payload was selected; every split recorded after the "
        "first download would be discarded")


def test_one_file_per_code_across_many_codes():
    picked = latest_files_by_code(P(
        "EVR.AU_2026-04-28.json.gz", "EVR.AU_2026-10-04.json.gz",
        "ENL.AU_2026-04-28.json.gz", "ENL.AU_2026-09-27.json.gz",
        "BHP.AU_2026-04-28.json.gz",
    ))
    names = sorted(p.name for p in picked)
    assert names == [
        "BHP.AU_2026-04-28.json.gz",
        "ENL.AU_2026-09-27.json.gz",
        "EVR.AU_2026-10-04.json.gz",
    ], names


def test_month_boundaries_sort_by_date_not_string_luck():
    """2026-10-04 must beat 2026-04-28 — the case an ascending sort got
    backwards, and the one that actually happened."""
    for older, newer in [
        ("X.AU_2026-04-28.json.gz", "X.AU_2026-10-04.json.gz"),
        ("X.AU_2026-09-30.json.gz", "X.AU_2026-10-01.json.gz"),
        ("X.AU_2025-12-31.json.gz", "X.AU_2026-01-01.json.gz"),
    ]:
        picked = latest_files_by_code(P(older, newer))
        assert picked[0].name == newer, f"{older} was preferred over {newer}"


def test_a_single_payload_is_returned_unchanged():
    picked = latest_files_by_code(P("AAA.AU_2026-04-28.json.gz"))
    assert [p.name for p in picked] == ["AAA.AU_2026-04-28.json.gz"]


def test_no_payloads_is_not_an_error():
    assert latest_files_by_code([]) == []


def test_the_code_is_parsed_off_the_filename():
    assert code_of(Path("EVR.AU_2026-10-04.json.gz")) == "EVR"
    assert code_of(Path("HGODB.AU_2026-08-19.json.gz")) == "HGODB"


def test_the_result_is_stable_in_name_order():
    """Two runs over the same directory must process in the same sequence,
    so a resumed or compared run lines up."""
    files = P("C.AU_2026-01-01.json.gz", "A.AU_2026-01-01.json.gz",
              "B.AU_2026-01-01.json.gz")
    assert ([p.name for p in latest_files_by_code(files)]
            == [p.name for p in latest_files_by_code(list(reversed(files)))])


# ── The union rule: every payload, because none is complete ────────────────

def test_every_payload_is_loaded_not_one_per_code():
    """Both single-file rules lose data, and we shipped both in one day.

    oldest-wins lost EVR's 2026-09-08 consolidation.
    newest-wins lost EVR's 2008 and 2017 consolidations, because EODHD's
    response for 2026-10-04 contained only the September record even though
    it was requested with from=2000-01-01. Across the exchange that cost 104
    split records.
    """
    files = P("EVR.AU_2026-04-28.json.gz", "EVR.AU_2026-10-04.json.gz")
    picked = [p.name for p in all_payloads_oldest_first(files)]
    assert picked == ["EVR.AU_2026-04-28.json.gz", "EVR.AU_2026-10-04.json.gz"], (
        "payloads were filtered; a payload omitting a split is not evidence "
        "that the split did not happen")


def test_payloads_are_applied_oldest_first():
    """So that ON CONFLICT DO UPDATE leaves the NEWEST description of a
    given split date in place: later writes win."""
    files = P("X.AU_2026-10-04.json.gz", "X.AU_2026-01-01.json.gz",
              "X.AU_2026-04-28.json.gz")
    assert [p.name for p in all_payloads_oldest_first(files)] == [
        "X.AU_2026-01-01.json.gz",
        "X.AU_2026-04-28.json.gz",
        "X.AU_2026-10-04.json.gz",
    ]


def test_the_union_keeps_every_code():
    files = P("A.AU_2026-01-01.json.gz", "A.AU_2026-06-01.json.gz",
              "B.AU_2026-01-01.json.gz")
    assert len(all_payloads_oldest_first(files)) == 3


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
