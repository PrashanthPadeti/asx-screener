"""
The sentinel's properties, enforced
===================================
On 2 Oct 2026 production was unavailable for ~40 minutes and nothing reported
it. `assert_output_freshness` asserts that the data is current; nothing
asserted that the site answers. This fixes that, and these tests pin the
properties that make the fix worth having.

The probe's own verdict logic is exercised by `uptime_probe.py --self-test`,
with no network. This file enforces the structural requirements that a passing
self-test cannot: that it runs outside the host, carries no secrets, sets
timeouts, identifies itself, and does not short-circuit on success.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_uptime_sentinel.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PROBE = REPO / ".github/scripts/uptime_probe.py"
WORKFLOW = REPO / ".github/workflows/uptime-sentinel.yml"


def _probe_src() -> str:
    return PROBE.read_text(encoding="utf-8")


def test_the_sentinel_exists_where_this_test_expects():
    assert PROBE.is_file(), f"{PROBE} is gone"
    assert WORKFLOW.is_file(), f"{WORKFLOW} is gone"


def test_it_runs_outside_the_host_it_observes():
    """A monitor hosted on the machine it watches tells you nothing when that
    machine is the problem — which is the exact condition it exists for."""
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in wf, "no longer runs on GitHub's infra"
    assert "schedule:" in wf and "cron:" in wf, "the sentinel is no longer scheduled"


def test_it_probes_both_the_page_and_an_uncached_api_path():
    src = _probe_src()
    assert '"/"' in src or 'BASE}/"' in src, "the homepage is not probed"
    assert "/api/v1/market/summary" in src, "no API path is probed"


def test_status_alone_is_not_accepted_as_health():
    """A site can answer 200 while serving nothing. In Oct 2026 this one
    shipped 68 KB of HTML containing ~1,000 characters of navbar and footer,
    so "answered" and "served the page" are different conditions here."""
    src = _probe_src()
    assert "total_stocks" in src, "no semantic assertion on the API response"
    assert "assert_body" in src, "no body assertion is wired into a target"


def test_an_empty_universe_is_a_failure():
    sys.path.insert(0, str(PROBE.parent))
    import uptime_probe                                        # noqa: PLC0415
    assert uptime_probe._summary_is_meaningful('{"total_stocks": 0}') is not None
    assert uptime_probe._summary_is_meaningful('{"total_stocks": 2121}') is None


def test_one_transient_does_not_raise_an_alarm():
    sys.path.insert(0, str(PROBE.parent))
    import uptime_probe                                        # noqa: PLC0415
    ok = {"ok": True, "status": 200, "latency_ms": 1, "failure": None}
    bad = {"ok": False, "status": None, "latency_ms": 1, "failure": "timeout"}
    assert uptime_probe.verdict([bad, ok, ok]) == "degraded"
    assert uptime_probe.exit_code({"homepage": "degraded"}) == 0
    assert uptime_probe.verdict([bad, bad, bad]) == "down"
    assert uptime_probe.exit_code({"homepage": "down"}) == 1


def test_observations_are_independent_and_not_short_circuited():
    """A run that goes 200 / timeout / 200 is materially different from
    200 / 200 / 200. Stopping at the first success would erase the failed
    sample, which is the one worth keeping."""
    src = _probe_src()
    loop = src[src.index("for i in range(OBSERVATIONS)"):src.index("v = verdict(")]
    assert "break" not in loop, "the probe stops early, discarding later samples"
    assert "continue" not in loop, "an observation can be skipped"
    assert "observations.append" in loop, "not every observation is recorded"


def test_every_observation_reports_status_latency_and_reason():
    src = _probe_src()
    assert "latency_ms" in src and "failure" in src and "status" in src
    printed = src[src.index('mark = "ok  "'):src.index("v = verdict(")]
    for field in ("status=", "latency=", "o['failure']"):
        assert field in printed, f"{field} is not printed per observation"


def test_requests_are_bounded_by_a_timeout():
    """Without a timeout the sentinel hangs exactly when the site hangs, and
    the run reports nothing rather than reporting the outage."""
    src = _probe_src()
    assert re.search(r"TIMEOUT_SECONDS\s*=\s*\d+", src), "no timeout constant"
    assert "timeout=timeout" in src, "the timeout is not passed to the request"


def test_the_sentinel_identifies_itself():
    """Cloudflare answers urllib's default agent with 403. This project has
    already had a checker report UNVERIFIED forever for that reason; here it
    would report a healthy site as down."""
    src = _probe_src()
    assert "User-Agent" in src, "the request does not identify itself"
    assert "asx-screener" in src, "identify honestly, do not borrow a browser UA"
    assert "Mozilla" not in src, "a borrowed browser user agent is a lie"


def test_it_carries_no_secrets():
    """A sentinel needing credentials cannot run in a public workflow, and a
    public repo is the wrong place to discover that."""
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in wf, "the workflow references a secret"
    src = _probe_src()
    for leak in ("api_token", "Authorization", "password", "Bearer"):
        assert leak not in src, f"{leak} appears in the probe"


def test_the_probe_verifies_itself_before_trusting_its_verdict():
    """If the evaluation logic is broken the run should say so, rather than
    reporting the site down."""
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "--self-test" in wf, "the workflow does not verify the probe first"
    assert wf.index("--self-test") < wf.index("Probe production"), (
        "the self-test must run before the live probe")


def test_the_record_does_not_overclaim_what_this_is():
    """It is detection and evidence, not paging. Saying so in the artefact
    keeps a future reader from treating a green workflow as an on-call."""
    for f in (PROBE, WORKFLOW):
        src = f.read_text(encoding="utf-8").lower()
        assert "not operational paging" in src or "not a pager" in src, (
            f"{f.name} no longer states its limits")


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
