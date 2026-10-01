"""
Drift detection that can actually detect drift
===============================================
Two consumers trust Cloudflare: nginx decides whose CF-Connecting-IP it
believes, ufw decides who may reach the web ports. Both were generated from a
single fetch on 1 Oct 2026, and Cloudflare changes those prefixes.

The properties worth testing are the ones a naive checker gets wrong:

  * nginx and ufw agreeing with EACH OTHER is not success. Both are compared
    against Cloudflare's current set independently, so two consumers that
    drifted together still fail.
  * a failed fetch is UNVERIFIED, never "no drift". An unreachable source
    proves nothing, and reporting that as clean is how a check becomes
    decorative.
  * IPv4 and IPv6 are evaluated separately. A missing IPv6 range is invisible
    in a combined count that IPv4 dominates.
  * comparison is semantic. `2400:CB00:0000::/32` and `2400:cb00::/32` are one
    network; a textual check reports drift on a formatting change and misses a
    real one hidden behind different spelling.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_cloudflare_ranges.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.cloudflare_ranges import (                     # noqa: E402
    ConsumerResult, evaluate, normalise, parse_nginx, parse_published,
    parse_ufw, render, ufw_allows_anywhere,
)

# A plausible published set: enough entries to clear the sanity floor.
V4 = "\n".join(f"10.{i}.0.0/20" for i in range(1, 16))
V6 = "\n".join(f"2400:cb0{i}::/32" for i in range(1, 8))


def _published():
    return parse_published(V4, V6)


def _consumer(name, v4_text, v6_text, anywhere=False):
    v4, v6, bad = parse_published(v4_text, v6_text)
    return ConsumerResult(name, v4, v6, bad, anywhere)


def _clean():
    return [_consumer("nginx", V4, V6), _consumer("ufw :80", V4, V6),
            _consumer("ufw :443", V4, V6)]


# ── The baseline, and the control ────────────────────────────────────────────

def test_everything_in_agreement_is_current():
    r = evaluate(_published(), _clean())
    assert r["state"] == "current"
    assert r["expected"] == {"ipv4": 15, "ipv6": 7}
    assert "PASS" in render(r)


def test_the_check_is_not_simply_always_current():
    """The mutation control. A checker hard-wired to pass would satisfy the
    test above and nothing below."""
    c = _clean()
    c[0] = _consumer("nginx", V4, "\n".join(V6.splitlines()[:-1]))
    assert evaluate(_published(), c)["state"] == "drift"


# ── Missing and extra, in each consumer, in each family ──────────────────────

def test_a_range_missing_from_nginx_is_drift():
    c = _clean()
    c[0] = _consumer("nginx", "\n".join(V4.splitlines()[:-1]), V6)
    r = evaluate(_published(), c)
    assert r["state"] == "drift"
    assert r["consumers"][0]["missing"] == ["10.15.0.0/20"]


def test_a_range_missing_from_ufw_is_drift():
    c = _clean()
    c[1] = _consumer("ufw :80", "\n".join(V4.splitlines()[:-1]), V6)
    r = evaluate(_published(), c)
    assert r["state"] == "drift"
    assert len(r["consumers"][1]["missing"]) == 1


def test_an_unexpected_range_is_drift():
    """Extra matters as much as missing: a range Cloudflare no longer
    publishes is someone else's address space being trusted to assert
    visitor identity."""
    c = _clean()
    c[0] = _consumer("nginx", V4 + "\n203.0.113.0/24", V6)
    r = evaluate(_published(), c)
    assert r["state"] == "drift"
    assert r["consumers"][0]["extra"] == ["203.0.113.0/24"]


def test_ipv6_is_evaluated_separately_from_ipv4():
    """A missing IPv6 range must not be masked by a correct IPv4 count."""
    c = _clean()
    c[2] = _consumer("ufw :443", V4, "\n".join(V6.splitlines()[:-1]))
    r = evaluate(_published(), c)
    assert r["state"] == "drift"
    assert r["consumers"][2]["ipv4"] == 15
    assert len(r["consumers"][2]["missing"]) == 1


# ── The two rules that matter most ───────────────────────────────────────────

def test_consumers_agreeing_with_each_other_is_not_success():
    """Both stale in the same way. A checker comparing a copy to a copy would
    call this clean, which is the whole failure this module exists to avoid."""
    stale4 = "\n".join(V4.splitlines()[:-2])
    c = [_consumer("nginx", stale4, V6), _consumer("ufw :80", stale4, V6),
         _consumer("ufw :443", stale4, V6)]
    r = evaluate(_published(), c)
    assert r["state"] == "drift"
    assert all(len(x["missing"]) == 2 for x in r["consumers"])


def test_a_failed_fetch_is_unverified_not_clean():
    r = evaluate(None, _clean(), fetch_error="connection timed out")
    assert r["state"] == "unverified"
    assert "timed out" in r["reason"]
    assert "not 'no drift'" in render(r)


def test_an_implausibly_small_published_set_is_unverified():
    """An error page that happens to parse must not become the expected set
    and silently condemn every real range as 'extra'."""
    r = evaluate(parse_published("1.2.3.0/24", "2400:cb00::/32"), _clean())
    assert r["state"] == "unverified"
    assert "implausibly small" in r["reason"]


def test_a_malformed_published_entry_is_unverified():
    r = evaluate(parse_published(V4 + "\nnot-a-cidr", V6), _clean())
    assert r["state"] == "unverified"
    assert "malformed" in r["reason"]


# ── Parsing ──────────────────────────────────────────────────────────────────

def test_comparison_is_semantic_not_textual():
    assert normalise("2400:CB00:0000::/32") == normalise("2400:cb00::/32")
    assert normalise("  173.245.48.0/20  ") == "173.245.48.0/20"
    assert normalise("# a comment") is None
    assert normalise("173.245.48.1/20") is None          # host bits set


def test_nginx_parsing_reads_the_directive_not_the_file():
    conf = """
    # set_real_ip_from 203.0.113.0/24;   <- commented out, must be ignored
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from   2400:cb00::/32 ;
    real_ip_header CF-Connecting-IP;
    """
    v4, v6, bad = parse_nginx(conf)
    assert v4 == {"173.245.48.0/20"} and v6 == {"2400:cb00::/32"} and not bad


def test_ufw_parsing_separates_ports_and_sees_anywhere():
    status = """Status: active

To                         Action      From
--                         ------      ----
OpenSSH                    ALLOW       Anywhere
80/tcp                     ALLOW       173.245.48.0/20
443/tcp                    ALLOW       173.245.48.0/20
80/tcp (v6)                ALLOW       2400:cb00::/32
8000/tcp                   ALLOW       198.51.100.0/24
443/tcp                    ALLOW       Anywhere
"""
    v4_80, v6_80, _ = parse_ufw(status, 80)
    v4_443, _, _ = parse_ufw(status, 443)
    assert v4_80 == {"173.245.48.0/20"} and v6_80 == {"2400:cb00::/32"}
    assert "198.51.100.0/24" not in v4_80, "a rule for another port was counted"
    assert v4_443 == {"173.245.48.0/20"}
    assert ufw_allows_anywhere(status, 443) is True
    assert ufw_allows_anywhere(status, 80) is False


def test_a_restored_anywhere_rule_is_drift_even_if_ranges_match():
    """Every range correct AND the bypass reopened. A range-only check would
    report clean on the worse condition."""
    c = _clean()
    c[1] = _consumer("ufw :80", V4, V6, anywhere=True)
    r = evaluate(_published(), c)
    assert r["state"] == "drift"
    assert r["consumers"][1]["allows_anywhere"] is True
    assert "bypass is open" in render(r)


# ── It must not be able to change anything ───────────────────────────────────

def test_the_evaluator_performs_no_mutation_and_no_io():
    """A bad fetch or a parsing defect must not be able to rewrite the origin
    firewall. Detection first; reconciliation is a separate decision."""
    import ast
    src = (BACKEND / "compute/engine/cloudflare_ranges.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)

    # No capability to reach anything. Checked by import, not by scanning for
    # the word "ufw" -- which appears legitimately in the docstring and in
    # parse_ufw's name. A string scan would have flagged the explanation
    # rather than the behaviour, which this file has already done once today.
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom)) and n.names}
    assert not ({"subprocess", "os", "requests", "urllib", "httpx", "socket",
                 "pathlib", "shutil"} & imported), imported

    # And no call that could execute or write anything, by name.
    dangerous = {"open", "exec", "eval", "system", "Popen", "run", "remove",
                 "unlink", "write_text", "chmod"}
    called = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not (dangerous & called), sorted(dangerous & called)


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
