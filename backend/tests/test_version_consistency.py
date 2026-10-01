"""
One version, declared three times
==================================
The version is stated in three places and nothing made them agree:

    VERSION                        read by backup.sh to name its output
    backend/app/core/config.py     APP_VERSION, served by the API
    frontend/package.json          reported by pm2

On 1 Oct 2026 the first was missed during the v11.0.0 bump. The failure is
quiet and badly timed: `backup.sh` names its directory `v${VERSION}_${DATE}`,
so backups of v11 code would have been filed under v10.0.0 — and the moment
that matters is a restore, when nobody is in a position to notice the label
is wrong.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_version_consistency.py
"""

import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))


def _declared() -> dict[str, str]:
    return {
        "VERSION": (REPO / "VERSION").read_text(encoding="utf-8").strip(),
        "config.py APP_VERSION": re.search(
            r'APP_VERSION:\s*str\s*=\s*"([^"]+)"',
            (BACKEND / "app/core/config.py").read_text(encoding="utf-8")).group(1),
        "frontend package.json": json.loads(
            (REPO / "frontend/package.json").read_text(encoding="utf-8"))["version"],
    }


def test_every_declaration_agrees():
    declared = _declared()
    assert len(set(declared.values())) == 1, (
        "the version is declared differently in each place: "
        + ", ".join(f"{k}={v}" for k, v in sorted(declared.items())))


def test_the_version_is_a_release_number():
    """A placeholder or a dev suffix reaching a backup label is worse than a
    wrong number, because it looks deliberate."""
    for where, value in _declared().items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", value), f"{where} = {value!r}"


def test_the_check_can_actually_fail():
    """The mutation control, run against a copy rather than the real files."""
    declared = _declared()
    tampered = dict(declared)
    tampered["VERSION"] = "9.9.9"
    assert len(set(tampered.values())) != 1


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
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
