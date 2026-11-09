"""The Gold -> Universe sidecars must still be what the statement says.

Eleven YAML files under database/stm/mappings/ carry the mapping document for
screener.universe. Their mechanical half -- the SELECT expression, the source
table and column, the join rule, the writer list -- is DERIVED from the
statement by backend/scripts/stm/universe_sidecars.py. Their authored half
lives in universe_prose.py and universe_prose_extra.py.

That arrangement has exactly one failure mode, and it is the one mapping
documents always fail by: the statement changes and the document does not.
Nothing about a YAML file announces that it has gone stale. It keeps reading
as a reviewed description of a system it no longer describes, which is worse
than having no document, because a reader checks it and stops looking.

So the check is regeneration and comparison. Re-emit into a temporary
directory from the current evidence and the current prose, and require the
committed files to match byte for byte. That catches both directions:

  * the statement moved          -> re-derived fields differ
  * someone edited a YAML        -> their edit is not in the prose module
                                    and would be destroyed on the next run

The second is worth as much as the first. A business rule written into a
generated file is prose that will be silently deleted, and the person who
wrote it will believe it is in the document.

This test does NOT check that the prose is true. Nothing can. It checks that
the evidence beside the prose is current, so a reader who finds the prose
wrong is at least looking at the right statement.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
MAPPINGS = ROOT / "database" / "stm" / "mappings"
EMITTER = BACKEND / "scripts" / "stm" / "universe_sidecars.py"

#: The files the emitter owns. Listed, not globbed: a file that stops being
#: emitted must fail here rather than quietly drop out of the comparison and
#: take its columns with it.
EMITTED = (
    "screener_universe_identity.yaml",
    "screener_universe_price.yaml",
    "screener_universe_returns.yaml",
    "screener_universe_valuation.yaml",
    "screener_universe_fundamentals.yaml",
    "screener_universe_growth.yaml",
    "screener_universe_signals.yaml",
    "screener_universe_market_structure.yaml",
    "screener_universe_scores.yaml",
    "screener_universe_unwritten.yaml",
    "screener_universe_lifecycle.yaml",
)

EXPECT_TOTAL_COLUMNS = 401


def _regenerate() -> Path:
    """Run the emitter with its output redirected to a temp copy.

    The emitter writes to database/stm/mappings by construction, so the
    committed files are copied aside, the emitter runs, the fresh output is
    moved to a temp directory and the originals are restored. A test that
    left the working tree modified would be its own defect.
    """
    tmp = Path(tempfile.mkdtemp(prefix="stm_sidecars_"))
    backup = tmp / "committed"
    backup.mkdir()
    for name in EMITTED:
        src = MAPPINGS / name
        assert src.exists(), (
            f"{name} is listed as emitted and is not in {MAPPINGS}. Either "
            f"it was deleted -- taking its columns out of the document -- or "
            f"EMITTED is stale.")
        shutil.copy2(src, backup / name)

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, str(EMITTER)], cwd=str(ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace")

    fresh = tmp / "fresh"
    fresh.mkdir()
    try:
        assert result.returncode == 0, (
            f"the emitter failed, so the document cannot be checked at all:\n"
            f"{result.stdout}\n{result.stderr}")
        for name in EMITTED:
            shutil.copy2(MAPPINGS / name, fresh / name)
    finally:
        for name in EMITTED:
            shutil.copy2(backup / name, MAPPINGS / name)

    return fresh


def test_the_emitted_sidecars_are_current():
    fresh = _regenerate()
    stale = []
    for name in EMITTED:
        committed = (MAPPINGS / name).read_text(encoding="utf-8")
        regenerated = (fresh / name).read_text(encoding="utf-8")
        if committed != regenerated:
            stale.append(name)

    assert not stale, (
        f"{stale} differ from what the current statement and prose produce.\n"
        f"Run `python backend/scripts/stm/universe_sidecars.py` from the "
        f"repo root and commit the result.\n"
        f"If the difference is prose you wrote directly into the YAML, move "
        f"it into backend/scripts/stm/universe_prose.py -- a generated file "
        f"will destroy it on the next run and it will read as reviewed until "
        f"then.")


def test_every_emitted_file_is_listed():
    """A new emitted file must join the comparison, not sit outside it."""
    on_disk = {p.name for p in MAPPINGS.glob("screener_universe_*.yaml")}
    unlisted = sorted(on_disk - set(EMITTED))
    assert not unlisted, (
        f"{unlisted} are emitted sidecars that EMITTED does not name, so "
        f"they are never checked for drift.")


def test_the_document_still_covers_every_target_column():
    """Coverage is re-derived rather than remembered.

    The emitter prints its own total. A silent drop -- a section routed to no
    file, a prose key deleted -- would otherwise leave the YAML smaller and
    this file still green.
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, str(EMITTER)], cwd=str(ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr

    line = [ln for ln in result.stdout.splitlines() if "columns emitted" in ln]
    assert line, f"the emitter printed no total:\n{result.stdout}"
    total = int(line[-1].split()[0])
    assert total == EXPECT_TOTAL_COLUMNS, (
        f"the emitter now covers {total} columns, expected "
        f"{EXPECT_TOTAL_COLUMNS}. If the table really changed, update this "
        f"constant in the same commit as the snapshot.")


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
