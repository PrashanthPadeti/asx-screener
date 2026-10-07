#!/usr/bin/env python
"""
`is_asx200` must mean S&P/ASX 200 membership
============================================
Measured 7 Oct 2026. Every scheduled run of `asx_indices` logged:

    EODHD route failed: Client error '404 Not Found' for url
    'https://eodhd.com/api/v4/components/ATOI.INDX?...'
      -- falling back to market-cap approximation
    Flags set - ASX20:20 ASX50:50 ASX100:100 ASX200:200 ASX300:300

So `is_asx200` held **the top 200 by market cap**, not the S&P/ASX 200 —
whose membership an S&P committee selects with liquidity and free-float rules
and rebalances quarterly. The site presents it as membership, in a screener
filter and a company badge. A number the system could not substantiate.

Three separate defects, all in this one job:

1. **Wrong endpoint.** `v4/components/{SYM}` 404s for every symbol;
   `fundamentals/{SYM}.INDX` returns 200 OK with a `Components` block.
2. **Two wrong tickers.** `is_asx20` pointed at ATOI (which is the ASX *100*)
   and `is_asx100` at AOAD, which does not exist in EODHD's INDX catalog at
   all. One 404 aborts the fetch loop, so all five flags fell through —
   fixing only the endpoint would still have failed.
3. **The reset lived on the dead path.** `market.companies_current` read
   29/61/114/220/321 where the universe correctly read 20/50/100/200/300:

       321 = 300 correct
           +  15 in market.companies but absent from screener.universe
           +   6 delisted rows inside screener.universe

Run:  python tests/test_index_membership_is_not_a_proxy.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ENGINE = BACKEND / "compute" / "engine" / "asx_indices.py"
sys.path.insert(0, str(BACKEND))


def _source() -> str:
    """Comments stripped. This file's own prose names the wrong tickers and
    the dead endpoint, and so does the module's. A scan that reads its own
    explanation reports the bug it just fixed -- six times in this codebase
    now."""
    raw = ENGINE.read_text(encoding="utf-8")
    tree = ast.parse(raw)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(body[0].value.value)
    out = []
    for line in raw.splitlines():
        if line.strip().startswith("#"):
            continue
        out.append(line)
    text = "\n".join(out)
    for d in docstrings:
        text = text.replace(d, "")
    return text


# ── 1. The endpoint ─────────────────────────────────────────────────────────

def test_the_constituent_endpoint_is_fundamentals():
    src = _source()
    assert "api/fundamentals/" in src, (
        "the constituent fetch does not use the fundamentals endpoint")
    assert "v4/components" not in src, (
        "the dead v4/components path is still in use; it 404s for every "
        "symbol, which is what forced the market-cap fallback daily")


# ── 2. The tickers ──────────────────────────────────────────────────────────

#: Verified 7 Oct 2026 by fetching each symbol and by EODHD's own INDX
#: exchange-symbol-list. Hardcoded deliberately: the point is that the map
#: agrees with the provider, so deriving the expectation from the map would
#: make the test agree with itself.
VERIFIED = {
    "is_asx20":  "ATLI.INDX",
    "is_asx50":  "AFLI.INDX",
    "is_asx100": "ATOI.INDX",
    "is_asx200": "AXJO.INDX",
    "is_asx300": "AXKO.INDX",
}


def _ticker_map() -> dict:
    import importlib.util
    spec = importlib.util.spec_from_file_location("_axi", ENGINE)
    # Import would require sqlalchemy/dotenv; read the literal instead.
    src = ENGINE.read_text(encoding="utf-8")
    block = src[src.index("EODHD_INDICES = {"):]
    block = block[:block.index("}") + 1]
    return dict(re.findall(r'"(is_asx\d+)":\s*"([A-Z]+\.INDX)"', block))


def test_every_index_ticker_matches_the_provider():
    actual = _ticker_map()
    assert actual == VERIFIED, (
        "index tickers disagree with EODHD's catalog: " +
        "; ".join(f"{k}: {actual.get(k)} != {v}"
                  for k, v in VERIFIED.items() if actual.get(k) != v))


def test_the_two_known_wrong_tickers_are_gone():
    """Mutation control, naming the exact prior values.

    ATOI on is_asx20 silently mislabels the ASX 100 as the ASX 20. AOAD does
    not exist, and one 404 aborts the whole fetch loop.
    """
    actual = _ticker_map()
    assert actual["is_asx20"] != "ATOI.INDX"
    assert "AOAD.INDX" not in actual.values()


# ── 3. Parsing ──────────────────────────────────────────────────────────────

def _codes_from_components():
    """The real function, lifted out of the module.

    Importing `asx_indices` pulls in dotenv and sqlalchemy for a function that
    needs neither. Executing its own source keeps this hermetic -- and it is
    the deployed source, not a copy, so the test cannot drift from it.
    """
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and n.name == "codes_from_components")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]),
                 str(ENGINE), "exec"), ns)
    return ns["codes_from_components"]


def test_components_parse_from_the_real_shape():
    codes_from_components = _codes_from_components()
    payload = {"General": {"Name": "S&P/ASX 200"},
               "Components": {"0": {"Code": "BHP", "Exchange": "AU"},
                              "1": {"Code": "CBA", "Exchange": "AU"}}}
    assert codes_from_components(payload) == {"BHP", "CBA"}


def test_a_mapping_is_not_iterated_as_keys():
    """`for item in components` yields "0", "1" -- the classic shape bug."""
    codes_from_components = _codes_from_components()
    payload = {"Components": {"0": {"Code": "BHP"}, "1": {"Code": "CBA"}}}
    got = codes_from_components(payload)
    assert "0" not in got and "1" not in got, got


def test_an_empty_or_missing_block_yields_nothing():
    codes_from_components = _codes_from_components()
    assert codes_from_components({}) == set()
    assert codes_from_components({"Components": {}}) == set()
    assert codes_from_components({"Components": None}) == set()


def test_a_list_shape_still_parses():
    """Tolerated in case the provider changes the container."""
    codes_from_components = _codes_from_components()
    assert codes_from_components(
        {"Components": [{"Code": "BHP.AU"}]}) == {"BHP"}


# ── 4. The reset, and the SCD predicate ─────────────────────────────────────

def test_the_clear_runs_on_whichever_path_executes():
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    for fname in ("_update_via_eodhd", "_update_via_market_cap"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == fname)
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)
                 and n.func.id == "_clear_all_flags"]
        assert calls, (
            f"{fname} never clears the flags. The clear used to live only on "
            f"the EODHD path -- the one that was failing -- which left 15 "
            f"codes outside the universe flagged forever")


def test_the_universe_clear_is_not_restricted_to_active():
    """6 delisted universe rows kept stale flags because the clear filtered
    `status = 'active'` and the rank CTE excluded them too."""
    src = _source()
    clear = src[src.index("UPDATE screener.universe\n        SET is_asx20=FALSE"):]
    clear = clear[:clear.index('"""')]
    assert "status" not in clear, (
        "the universe clear still filters on status, so non-active rows keep "
        "flags no later step recomputes")


def test_company_writes_carry_the_currency_predicate():
    """market.companies is SCD Type 2. Without `is_current` the clear wipes
    flags from superseded rows and the set marks them TRUE, rewriting what
    was true historically."""
    src = _source()
    offenders = []
    for m in re.finditer(r"UPDATE market\.companies", src):
        stmt = src[m.start():m.start() + 700]
        stop = stmt.find('"""')
        stmt = stmt[:stop if stop > 0 else len(stmt)]
        if "is_current" not in stmt:
            offenders.append(stmt.splitlines()[0].strip())
    assert not offenders, (
        "these writes to market.companies have no is_current predicate: "
        + "; ".join(offenders))


# ── 5. The proxy may not be silent ──────────────────────────────────────────

def test_the_market_cap_fallback_is_not_automatic():
    """A proxy written into is_asx200 answers a different question under the
    same name. It ran automatically on any error, and did so every day."""
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    run = next(n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "run")
    names = {a.arg for a in run.args.args}
    assert "market_cap_approximation" in names, (
        "run() has no explicit opt-in for the proxy")

    raises = [n for n in ast.walk(run) if isinstance(n, ast.Raise)]
    assert raises, (
        "run() cannot fail when the real source is unavailable, so it still "
        "substitutes a proxy silently")


def test_the_failure_is_the_governed_producer_type():
    """So it reaches ops.job_executions through the v11.2.11 wrapper chain."""
    src = _source()
    assert "ProducerFailure" in src
    from compute.engine.producer_contract import ProducerFailure
    assert issubclass(ProducerFailure, Exception)


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
            except Exception as exc:                       # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
