#!/usr/bin/env python
"""
Every entitlement claim must correspond to a real enforcement path
==================================================================
The pricing table is a contract shown to a buyer. Its access rows are
*declared by hand*, because "which surfaces a plan can open" has no
representation in PLAN_LIMITS, and a declaration can be wrong. Seven rows
were wrong in a single week, in three distinct directions:

    AI Screener           ticked for Pro; nl_screener is Premium
    ASX market overview   ticked for Free; three of five panels were Pro-gated
    Sector screens        crossed for Free; there is no gate on them at all
    News                  ticked for Free; the Watchlist News tab is Pro
    Announcement history  the page claims a Free cap that does not exist
    Announcement AI       the page sells Premium summaries that do not exist
    watchlist_only        comment says "Pro+"; the API checks no plan

The third and fifth are why a syntax-only scan is not enough. They claim
restrictions that **exist nowhere** -- no PlanGate, no isPro, nothing. A guard
that only looked for gates would have found none and had no opinion.

So each row names the enforcement path it believes in, this test verifies that
path really exists in the source, and then DERIVES the expected
free/pro/premium triple from it.

    row -> declared mechanism -> verified against source -> derived triple
                                                         -> compared to table

Fail-closed, three ways
-----------------------
1. A row with no declared mechanism fails; it is never read as Free.
2. A mechanism that cannot confirm itself raises rather than returning a
   default, so a deleted gate fails loudly.
3. A plan lock in the source that no row accounts for fails -- `shared_page`.
   This is the one that found the News defects: a page can host several
   features, so "the page is reachable" says nothing about the features on
   it. /market had a PlanGate-free page with three Pro-locked panels.

What this cannot prove
----------------------
That a Free user actually receives what the table promises.

    A structural guard proves the enforcement machinery exists.
    Only behavioural evidence proves the customer receives the entitlement.

The manual Free-user sweep is the oracle. Where it disagrees with this file,
this file is wrong.

Run:  python tests/test_pricing_table_matches_enforcement.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
PRICING = FRONTEND / "app" / "pricing" / "page.tsx"

sys.path.insert(0, str(BACKEND))
from app.core.plans import PLAN_LIMITS                       # noqa: E402

TIERS = ("free", "pro", "premium")
RANK = {"free": 0, "pro": 1, "premium": 2}

#: What counts as a plan lock in TSX. Negation of a plan flag, or a tab/item
#: declaring its own gate. Deliberately NOT `min_plan === 'premium'` or
#: `upgradeForTier === 'pro'` -- those classify an item or render a modal;
#: they do not withhold anything by themselves.
LOCK = re.compile(r"!\s*is(?:Pro|Premium)\b|\.gate\s*===|\bgate:\s*'(?:pro|premium)'")


# ── Mechanisms ──────────────────────────────────────────────────────────────
# Each returns the minimum tier that can reach the surface, having first
# PROVEN the mechanism is present.

def _page(page: str) -> str:
    return (FRONTEND / "app" / page / "page.tsx").read_text(encoding="utf-8")


def plan_gate(page: str, expect: str) -> str:
    """A <PlanGate required="..."> wrapping a whole page."""
    src = _page(page)
    m = re.search(r'PlanGate[^>]*required="([a-z_]+)"', src)
    if not m:
        raise AssertionError(f"app/{page}/page.tsx has no PlanGate; the table "
                             f"claims a {expect} restriction that is not there")
    if m.group(1) != expect:
        raise AssertionError(f"app/{page}/page.tsx gates on {m.group(1)!r}, "
                             f"the table implies {expect!r}")
    return expect


def open_page(page: str) -> str:
    """No PlanGate and no plan lock anywhere. Free reaches all of it."""
    src = _page(page)
    if "PlanGate" in src:
        raise AssertionError(f"app/{page}/page.tsx has a PlanGate; the table "
                             f"says it is free")
    # /market keeps its ProGate branches but forces the flag open, so
    # re-gating is one line. A forced-open flag is not a lock.
    if re.search(r"const\s+isPro\s*=\s*true", src):
        return "free"
    bad = [f"line {n}: {l.strip()[:70]}"
           for n, l in enumerate(src.splitlines(), 1) if LOCK.search(l)]
    if bad:
        raise AssertionError(
            f"app/{page}/page.tsx locks content while the table says the page "
            f"is free -- the /market defect:\n      " + "\n      ".join(bad))
    return "free"


def shared_page(page: str, accounted: tuple[str, ...]) -> str:
    """A page hosting several features, each of which is a row of its own.

    Reaching the page is free; the locks inside it belong to OTHER rows, which
    must be named in `accounted`. A lock matching nothing fails: either a free
    feature has just been gated, or a gated feature is missing from the table.

    Replacing a blunt "no locks on this page" check with this is what exposed
    the News defects -- that check could only be satisfied by exempting the
    whole file, which is how four undeclared locks sat there unseen.
    """
    src = _page(page)
    if "PlanGate" in src:
        raise AssertionError(f"app/{page}/page.tsx has a PlanGate; the table "
                             f"says the page itself is free")
    orphans, seen = [], set()
    for n, line in enumerate(src.splitlines(), 1):
        if not LOCK.search(line):
            continue
        owner = next((a for a in accounted if a in line), None)
        if owner is None:
            orphans.append(f"line {n}: {line.strip()[:70]}")
        else:
            seen.add(owner)
    if orphans:
        raise AssertionError(
            f"app/{page}/page.tsx has plan locks no pricing row accounts for; "
            f"a buyer is not told about these:\n      " + "\n      ".join(orphans))
    missing = set(accounted) - seen
    if missing:
        raise AssertionError(
            f"app/{page}/page.tsx no longer contains the locks this row relies "
            f"on, so the restriction is unverified: {sorted(missing)}")
    return "free"


def backend_flag(flag: str) -> str:
    """A PLAN_LIMITS boolean. Minimum tier where it is True."""
    for tier in TIERS:
        if PLAN_LIMITS[tier][flag]:
            return tier
    raise AssertionError(f"PLAN_LIMITS[{flag!r}] is False on every tier, so "
                         f"the table cannot be offering it to anyone")


def _contains(root: Path, path: str, needle: str, minimum: str) -> str:
    src = (root / path).read_text(encoding="utf-8")
    if needle not in src:
        raise AssertionError(f"{path} no longer contains {needle!r}, so the "
                             f"{minimum!r} restriction is unverified")
    return minimum


def frontend_contains(path: str, needle: str, minimum: str) -> str:
    """A named guard in a frontend file. Root passed explicitly: inferring it
    from the path sent `app/screener/page.tsx` to the backend."""
    return _contains(FRONTEND, path, needle, minimum)


def backend_contains(path: str, needle: str, minimum: str) -> str:
    """A named guard in a backend file."""
    return _contains(BACKEND, path, needle, minimum)


def no_gate_anywhere(path: str, marker: str) -> str:
    """A surface rendered with no lock at all -- the Sector-screens case.

    Asserted positively: the marker must be present AND unlocked. Claiming a
    restriction here is what the table did wrong.
    """
    src = (FRONTEND / path).read_text(encoding="utf-8")
    if marker not in src:
        raise AssertionError(f"{path} no longer renders {marker!r}; the row "
                             f"maps to a surface that has moved")
    block = src[src.index(marker): src.index(marker) + 900]
    if re.search(r"\blocked\b", block) or LOCK.search(block):
        raise AssertionError(f"{path} now locks {marker!r}; the table says it "
                             f"is free to everyone")
    return "free"


#: Locks on pages that host more than one priced feature. Each string must be
#: the row that owns it; `shared_page` fails on anything else in the file.
SCREENER_LOCKS = (
    "tier === 'premium' && !isPremium",     # Premium screens  (preset modal)
    "tier === 'pro'     && !isPro",         # Pro screens      (preset modal)
    "!isAdmin && !isPro",                   # Query Mode
)
#: /news needs no entry: every lock was removed on 8 Oct 2026, so it is an
#: `open_page`. It is named here because this is where the next person will
#: look if a tab gets gated again -- give the feature a pricing row and switch
#: the row to shared_page(), rather than exempting the file.
SCANS_LOCKS = (
    "preset.premium && !isPro",             # Pro screens
    "{!isPremium && (",                     # Premium screens  (section header)
    "{!isPro && (",                         # Pro screens      (section header)
)

#: Every access row, with the enforcement path it claims. A row missing from
#: here fails `test_every_row_is_classified` rather than being assumed Free.
ROWS: dict[str, callable] = {
    "Screener — filters":             lambda: shared_page("screener", SCREENER_LOCKS),
    "Screener — Query Mode":          lambda: frontend_contains(
        "app/screener/page.tsx", "!isAdmin && !isPro", "pro"),
    "Screener — AI natural language": lambda: backend_flag("nl_screener"),
    "CSV export":                     lambda: backend_flag("csv_export"),
    "AI portfolio insights":          lambda: backend_flag("portfolio_insights"),

    "Quick screens":                  lambda: no_gate_anywhere(
        "app/scans/page.tsx", "presetTier"),
    "Sector screens":                 lambda: no_gate_anywhere(
        "app/scans/page.tsx", "sectors.map"),
    "Pro screens":                    lambda: frontend_contains(
        "app/scans/page.tsx", "preset.premium && !isPro", "pro"),
    "Premium screens":                lambda: frontend_contains(
        "app/scans/page.tsx", "isPro={isPremium}", "premium"),
    "Community screens":              lambda: backend_contains(
        "app/api/v1/routes/saved_screens.py", "rank_filter = user_rank", "pro"),
    "Saved screens":                  lambda: shared_page("screener", SCREENER_LOCKS),

    "ASX market overview":            lambda: open_page("market"),
    "Highs, Lows & Volume":           lambda: open_page("market"),
    "Volume activity":                lambda: open_page("market"),
    "Market anomalies":               lambda: open_page("market"),

    # Every tab is free, Watchlist News included -- the watchlist entitlement
    # is a count, not an access gate. `open_page` rather than `shared_page`,
    # so re-gating any tab fails this row instead of needing a new one.
    "News":                           lambda: open_page("news"),

    "Short interest data":            lambda: backend_contains(
        "app/api/v1/routes/screener.py", '"short_pct"', "free"),
    "Education hub":                  lambda: open_page("education"),

    "Metrics glossary":               lambda: plan_gate("glossary", "pro"),
    "Broker compare":                 lambda: plan_gate("brokers", "pro"),
    "ASX indices":                    lambda: plan_gate("indices", "premium"),
    "ETFs & funds":                   lambda: plan_gate("funds", "premium"),
    "Commodities":                    lambda: plan_gate("commodities", "premium"),
    "Global markets":                 lambda: plan_gate("global-markets", "premium"),
    "Performance heatmap":            lambda: plan_gate("market/heatmap", "premium"),
    "AlphaFive weekly picks":         lambda: plan_gate("top5", "premium"),
}

#: Numeric rows, checked against PLAN_LIMITS by test_plan_entitlements.py.
LIMIT_ROWS = {"Portfolios", "Watchlists", "Stocks per watchlist", "Price alerts"}

#: Cells whose text qualifies the access rather than granting it outright.
#: Declared, not inferred: any OTHER non-boolean cell fails as unverified,
#: because "some string is truthy" is how 'Pro tier' would have hidden a
#: downgrade to 'Pro only on request'.
QUALIFIED = {("Community screens", "pro"): "'Pro tier'"}

#: camelCase in frontend/lib/plans.ts -> snake_case in app/core/plans.py.
FLAG_NAMES = {"nlScreener": "nl_screener", "csvExport": "csv_export",
              "portfolioInsights": "portfolio_insights"}


def _table() -> dict[str, tuple]:
    """(free, pro, premium) per row, verbatim from the deployed source."""
    src = PRICING.read_text(encoding="utf-8")
    block = src[src.index("const FEATURE_ROWS"):src.index("// ── Component")]
    out = {}
    for m in re.finditer(
            r"\{\s*label:\s*'([^']+)',\s*free:\s*([^,]+),\s*pro:\s*([^,]+),"
            r"\s*premium:\s*([^}]+?)\s*\}", block):
        out[m.group(1)] = tuple(v.strip().rstrip(",").strip()
                                for v in m.groups()[1:])
    return out


def _cell(label: str, tier: str, raw: str) -> str:
    """Resolve a table cell to 'true' / 'false', or raise if it cannot be.

    `L.premium.nlScreener` is read back out of PLAN_LIMITS rather than assumed
    truthy -- treating every non-boolean as 'true' is what made the first run
    of this guard agree with four rows it should have failed.
    """
    if raw in ("true", "false"):
        return raw
    m = re.fullmatch(r"L\.(\w+)\.(\w+)", raw)
    if m:
        plan, flag = m.group(1), FLAG_NAMES.get(m.group(2), m.group(2))
        if plan not in PLAN_LIMITS or flag not in PLAN_LIMITS[plan]:
            raise AssertionError(f"{label}/{tier} reads {raw}, which is not a "
                                 f"PLAN_LIMITS field")
        return "true" if PLAN_LIMITS[plan][flag] else "false"
    if QUALIFIED.get((label, tier)) == raw:
        return "true"
    raise AssertionError(
        f"{label}/{tier} is {raw}, neither a boolean nor a declared "
        f"qualification; the claim cannot be verified, so it fails closed")


def _expected(minimum: str) -> tuple:
    return tuple("true" if RANK[t] >= RANK[minimum] else "false" for t in TIERS)


# ── Tests ───────────────────────────────────────────────────────────────────

def test_every_row_is_classified():
    """No row may be unmapped. An unmapped row would otherwise read as Free."""
    table = _table()
    assert table, "could not parse FEATURE_ROWS"
    unmapped = set(table) - set(ROWS) - LIMIT_ROWS
    assert not unmapped, (
        "pricing rows with no declared enforcement path -- a buyer is being "
        "shown a claim nothing verifies: " + ", ".join(sorted(unmapped)))
    stale = set(ROWS) - set(table)
    assert not stale, (
        "declared paths for rows no longer in the table: "
        + ", ".join(sorted(stale)))


def test_every_claim_matches_its_enforcement():
    table = _table()
    problems = []
    for label, resolve in ROWS.items():
        if label not in table:
            continue                       # reported by the test above
        try:
            minimum = resolve()
            got = tuple(_cell(label, t, c) for t, c in zip(TIERS, table[label]))
        except AssertionError as exc:
            problems.append(f"{label}: {exc}")
            continue
        except (OSError, ValueError) as exc:
            problems.append(f"{label}: could not resolve surface ({exc})")
            continue
        want = _expected(minimum)
        if got != want:
            problems.append(f"{label}: enforced from {minimum!r} -> expected "
                            f"{want}, table says {table[label]}")
    assert not problems, "\n  ".join([""] + problems)


# ── Mutation controls ───────────────────────────────────────────────────────

def test_the_sector_screens_defect_would_be_caught():
    """Control 1 — the row that started this.

    Sector screens are ungated, so a table claiming any restriction must fail.
    """
    minimum = ROWS["Sector screens"]()
    assert minimum == "free"
    assert _expected("free") == ("true", "true", "true")
    assert _expected("pro") != _expected("free"), (
        "the guard cannot distinguish a restricted row from a free one")


def test_a_removed_gate_would_be_caught():
    """Control 2 — a Premium gate deleted from source.

    `plan_gate` must raise rather than return a default, so a page that lost
    its PlanGate fails loudly instead of reading as free.
    """
    try:
        plan_gate("news", "premium")          # /news has no PlanGate
    except AssertionError:
        return
    raise AssertionError(
        "plan_gate tolerates a missing gate, so deleting one would not fail")


def test_an_in_component_lock_is_caught():
    """Control 3 — the /market defect.

    A page with no PlanGate but an isPro lock inside must not pass as free.
    """
    import tempfile
    d = Path(tempfile.mkdtemp()) / "app" / "faux"
    d.mkdir(parents=True)
    (d / "page.tsx").write_text(
        "export default function P(){ return <>{!isPro ? <Gate/> : <Real/>}</> }",
        encoding="utf-8")
    global FRONTEND
    real, FRONTEND = FRONTEND, d.parents[1]
    try:
        open_page("faux")
    except AssertionError:
        return
    finally:
        FRONTEND = real
    raise AssertionError(
        "open_page ignores in-component locks, which is exactly how the "
        "ASX market overview row was wrong")


def test_an_undeclared_lock_on_a_shared_page_is_caught():
    """Control 4 — the News defect.

    A shared page is allowed to contain locks, but only ones a row owns.
    Gating a new feature without adding its row must fail.
    """
    import tempfile
    d = Path(tempfile.mkdtemp()) / "app" / "faux"
    d.mkdir(parents=True)
    (d / "page.tsx").write_text(
        "const a = tier === 'pro' && !isPro\n"
        "const b = somethingNew && !isPremium\n",
        encoding="utf-8")
    global FRONTEND
    real, FRONTEND = FRONTEND, d.parents[1]
    try:
        shared_page("faux", ("tier === 'pro' && !isPro",))
    except AssertionError as exc:
        assert "somethingNew" in str(exc), (
            "the failure does not name the unaccounted lock")
        return
    finally:
        FRONTEND = real
    raise AssertionError(
        "shared_page accepts a lock no pricing row declares, which is how "
        "the Watchlist News gate stayed invisible to a buyer")


def test_a_truthy_cell_cannot_launder_a_false_flag():
    """Control 5 — the bug in this guard's own first draft.

    `L.pro.nlScreener` is False. Normalising non-booleans to 'true' made four
    rows agree with a table that contradicted PLAN_LIMITS.
    """
    assert _cell("Screener — AI natural language", "pro",
                 "L.pro.nlScreener") == "false"
    assert _cell("Screener — AI natural language", "premium",
                 "L.premium.nlScreener") == "true"
    try:
        _cell("Some row", "free", "'Coming soon'")
    except AssertionError:
        return
    raise AssertionError(
        "an undeclared string cell passed; a row reading 'Coming soon' would "
        "be scored as granted access")


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}{exc}")
                failures.append(name)
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
