"""
The front door obeys the same rule as the backend
==================================================
P0-A exists so that no number is served which the system cannot substantiate.
Every gate built for that sits behind the API. The public landing page sat in
front of it, and until 2 Oct 2026 it rendered this:

    const PREVIEW_STOCKS = [
      { code: 'BHP', name: 'BHP Group', price: 43.82, pe: 11.4, roe: 28.1, ... },
      ...

Eight identifiable listed companies with invented price, P/E, dividend yield,
ROE and RSI, under the caption "Sample preview only -- open the full screener
for latest available data", which reads as STALE rather than FABRICATED. A
visitor had no way to draw that distinction.

The figures were not close. Measured against the live screener the same day:

    BHP   advertised $43.82   actual $60.26    (27% low)
    BHP   advertised ROE 28.1%   actual 19.5%
    BHP   advertised P/E 11.4x   actual: NOT AVAILABLE
    RIO   advertised $118.20  actual $162.85
    CBA   advertised $138.50  actual $149.71

The P/E line is the sharpest one. The applicability contract deliberately
declines to publish a P/E for BHP, because it cannot substantiate one -- and
the landing page printed 11.4x anyway. The gate worked; the page went around
it.

Why this test lives in backend/tests
------------------------------------
The frontend has no test runner (package.json: dev, build, start, lint). Adding
one to hold a single structural rule would be more machinery than the rule is
worth, and leaving the rule unenforced is how it drifted in the first place.

Why it strips comments first
----------------------------
This repo has read prose as code five separate times -- a test matching its own
docstring, a scan matching its own explanation, a docstring sentence recorded as
a SQL write. The replacement comment in page.tsx quotes the defect it replaced,
including the literal `BHP $43.82`. A scanner that did not strip comments would
flag the explanation and call it a regression.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_landing_page_no_fabricated_data.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PAGE = BACKEND.parent / "frontend/app/page.tsx"

#: Financial fields that must never be assigned a numeric literal in source.
#: A real row carries these from the API; a literal means someone typed a price.
MONEY_FIELDS = ("price", "pe", "pe_ratio", "roe", "rsi", "rsi_14",
                "yield", "dividend_yield", "market_cap")


def _executable_source(text: str) -> str:
    """TSX with // line comments and /* */ blocks removed.

    String literals are left intact: a legitimate `price:` assignment inside a
    string is still worth flagging, and no quoted text in this file spans the
    forms below.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def test_the_landing_page_exists_where_this_test_expects():
    assert PAGE.is_file(), f"{PAGE} moved; this test proves nothing until repointed"


def test_no_financial_field_is_assigned_a_numeric_literal():
    """The defect's exact shape: `price: 43.82` in a source file."""
    src = _executable_source(PAGE.read_text(encoding="utf-8"))
    pattern = re.compile(
        rf"\b({'|'.join(MONEY_FIELDS)})\s*:\s*-?\d+(\.\d+)?\b")
    hits = [m.group(0) for m in pattern.finditer(src)]
    assert not hits, (
        f"hardcoded financial values on the landing page: {hits}. "
        f"Serve real figures or render nothing.")


def test_the_scanner_would_actually_catch_the_original_defect():
    """Mutation control. A scanner that matched nothing would pass the test
    above forever. Feed it the deleted line and it must fire."""
    original = ("const PREVIEW_STOCKS = [\n"
                "  { code: 'BHP', name: 'BHP Group', price: 43.82, pe: 11.4, "
                "yield: 5.2, roe: 28.1, rsi: 54.2 },\n]\n")
    pattern = re.compile(
        rf"\b({'|'.join(MONEY_FIELDS)})\s*:\s*-?\d+(\.\d+)?\b")
    found = [m.group(1) for m in pattern.finditer(_executable_source(original))]
    assert set(found) >= {"price", "pe", "yield", "roe", "rsi"}, found


def test_the_comment_explaining_the_defect_is_not_itself_flagged():
    """The prose-as-code control. page.tsx quotes `BHP $43.82` in a comment by
    design; stripping must remove it, and must not remove real code."""
    raw = PAGE.read_text(encoding="utf-8")
    assert "43.82" in raw, (
        "the explanatory comment was removed; this control no longer proves "
        "that comments are stripped rather than absent")
    assert "43.82" not in _executable_source(raw), (
        "comment stripping failed -- the explanation is being read as code")


def test_the_preview_table_is_fed_by_a_fetch_not_a_constant():
    """Absence of literals is necessary but not sufficient: an empty table
    would also pass. The rows must come from the screener."""
    src = _executable_source(PAGE.read_text(encoding="utf-8"))
    assert "PREVIEW_STOCKS" not in src, "the fabricated constant is back"
    assert "fetchPreviewRows" in src
    assert "/api/v1/screener" in src


def test_unavailable_rows_hide_the_section_rather_than_substituting():
    """The fallback must be nothing, not remembered numbers -- the same
    storage-versus-serving discipline used throughout P0-A."""
    src = _executable_source(PAGE.read_text(encoding="utf-8"))
    assert "hasPreview" in src, "no guard: the section renders regardless"
    fn = src[src.index("async function fetchPreviewRows"):]
    fn = fn[:fn.index("\n}\n") + 3]
    assert "return []" in fn, "the failure path must yield no rows"
    assert not re.search(r"\b\d+\.\d+\b", fn), (
        "a numeric literal inside the fetcher suggests a fabricated fallback")


def test_no_expiry_deadline_is_advertised():
    """The landing and pricing pages advertised 'offer ends September 2026' as
    prose, in five places. The deadline passed on 30 Sep and the site kept
    advertising it, because nothing connected the copies.

    The decision taken on 2 Oct 2026 was to drop the deadline rather than move
    it: a date that must be hand-maintained to stay true will eventually stop
    being true, and the pricing page already gates the offer on a backend
    `founding.available` flag, which is the real signal. No date can expire if
    no date is published.
    """
    months = (r"(January|February|March|April|May|June|July|August|September|"
              r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|"
              r"Nov|Dec)")
    for page in ("frontend/app/page.tsx", "frontend/app/pricing/page.tsx"):
        src = _executable_source(
            (BACKEND.parent / page).read_text(encoding="utf-8"))
        assert not re.search(rf"{months}\s+20\d\d", src), (
            f"a literal month/year deadline is back in {page}")
        assert not re.search(r"[Oo]ffer ends|[Ee]nds\s+\{", src), (
            f"{page} advertises an expiry again")


def test_offer_availability_still_comes_from_the_backend():
    """Removing the deadline must not remove the ability to end the offer.
    The pricing page keeps gating on founding.available, so the offer can
    still be withdrawn -- by the system, not by a date typed into markup."""
    src = _executable_source(
        (BACKEND.parent / "frontend/app/pricing/page.tsx").read_text(
            encoding="utf-8"))
    assert "founding.available" in src, (
        "the availability gate was removed along with the deadline")
    assert "Offer has ended" in src, "no copy remains for the withdrawn state"


#: Public marketing surfaces. Admin pages are excluded: they are internal, and
#: their numbers are documentation of the system rather than claims to buyers.
PUBLIC_PAGES = (
    "frontend/app/page.tsx",
    "frontend/app/pricing/page.tsx",
    "frontend/app/screener/page.tsx",
    "frontend/app/learn",
    "frontend/app/resources",
    "frontend/app/data-freshness",
    "frontend/app/ai-insights-limitations",
    "frontend/app/brokers",
)


#: A scale claim stated as a literal. `(?:more\s+)?` matters: the landing page
#: said "and 40+ more metrics", and a pattern demanding the noun immediately
#: after the number walked straight past it.
_SCALE_CLAIM = re.compile(
    r"\b\d{1,3},?\d{3}\+?\s*(?:ASX|stocks|companies)"        # 2,000+ ASX
    r"|\b\d{2,4}\+\s*(?:\w+\s+)?(?:fields|metrics)"          # 235+ fields / 80+ screener metrics
    r"|\b\d{2,4}\+\s*ASX\b")                                 # 200+ ASX


def _public_sources():
    for rel in PUBLIC_PAGES:
        p = BACKEND.parent / rel
        files = sorted(p.rglob("*.tsx")) if p.is_dir() else [p]
        for f in files:
            yield f, _executable_source(f.read_text(encoding="utf-8"))


def test_no_page_states_its_own_universe_or_field_count():
    """On 2 Oct 2026 the universe size appeared in nine places across eight
    files and disagreed with itself -- 2,100+, 2,000+ and 2,000 companies all
    describing one 2,121-row universe. The field count disagreed four ways
    (235+, 200+, 80+, 40+) against a live 309.

    None were false that day. That is the point: nobody maintained them, and
    nothing would have noticed them becoming false.
    """
    claim = _SCALE_CLAIM
    offenders = []
    for path, src in _public_sources():
        for m in claim.finditer(src):
            offenders.append(f"{path.name}: {m.group(0).strip()}")
    assert not offenders, (
        "hardcoded scale claims found; import them from lib/claims.ts so one "
        f"edit changes them everywhere: {offenders}")


def test_the_scale_scanner_catches_every_claim_that_was_actually_there():
    """Mutation control, built from the real strings removed on 2 Oct 2026.

    The first version of this pattern caught seven of the eight. It missed
    "and 40+ more metrics" because a word sat between the number and the noun
    -- a near miss that would have left the landing page's own claim
    unguarded while the test reported success.
    """
    removed = [
        "Filter 2,100+ ASX stocks by P/E, ROE,",
        "narrow the 2,000+ ASX-listed companies",
        "The ASX lists over 2,000 companies.",
        "All 235+ fields available by name or alias",
        "ASX Screener includes 80+ metrics including",
        "across all 200+ ASX stocks.",
        "and 40+ more metrics.",
        "All 80+ screener metrics are recomputed each night.",
        "across 200+ fields.",
    ]
    missed = [s for s in removed if not _SCALE_CLAIM.search(s)]
    assert not missed, f"the scanner would not have caught: {missed}"


def test_the_scale_scanner_does_not_fire_on_everything():
    """The other half of the control. A pattern matching any number would
    satisfy the test above and condemn ordinary copy."""
    innocent = [
        "Shares held for 12+ months qualify for the 50% CGT discount.",
        "a 4% dividend with full franking is worth up to 5.7% gross",
        "1D / 1W / 1M / 3M return",
        "Filter {UNIVERSE_CLAIM} ASX stocks by P/E",
    ]
    fired = [s for s in innocent if _SCALE_CLAIM.search(s)]
    assert not fired, f"false positives: {fired}"


def test_the_scale_claims_are_declared_in_one_module():
    claims = BACKEND.parent / "frontend/lib/claims.ts"
    assert claims.is_file(), "lib/claims.ts is gone; the numbers have scattered"
    src = claims.read_text(encoding="utf-8")
    for name in ("UNIVERSE_FLOOR", "SCREENER_FIELDS_FLOOR"):
        assert re.search(rf"export\s+const\s+{name}\s*=\s*\d+", src), name


def test_the_claim_check_reads_the_floors_rather_than_restating_them():
    """A checker holding its own copy of the floors would verify itself and
    pass while the site drifted. It must parse claims.ts."""
    script = BACKEND / "scripts/assert_marketing_claims.py"
    assert script.is_file()
    src = script.read_text(encoding="utf-8")
    assert "claims.ts" in src and "CLAIMS_TS" in src
    body = src[src.index("def declared_floors"):src.index("def live_values")]
    assert "2000" not in body and "300" not in body, (
        "the checker restates a floor instead of reading it")


def test_the_claim_check_cannot_modify_what_it_measures():
    """Instrument isolation: the observer must not join the system it
    observes. A read-only session, and no write verbs."""
    src = (BACKEND / "scripts/assert_marketing_claims.py").read_text(
        encoding="utf-8")
    assert "set_session(readonly=True)" in src
    for verb in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER",
                 "commit()"):
        assert verb not in _executable_source(src), f"{verb} in an instrument"


def test_an_unreachable_source_is_unverified_not_passing():
    """A check that reports success when it could not measure anything is
    decorative. Same rule as the Cloudflare range checker."""
    src = (BACKEND / "scripts/assert_marketing_claims.py").read_text(
        encoding="utf-8")
    assert src.count("return 2") >= 3, (
        "failure-to-measure must exit 2 (unverified), distinct from exit 1")


def test_no_page_appends_the_site_name_the_layout_already_appends():
    """app/layout.tsx sets `template: '%s | ASX Screener'`, so a page title of
    'Data Freshness Policy | ASX Screener' renders as

        Data Freshness Policy | ASX Screener | ASX Screener

    which is what Google showed for 44 pages on 2 Oct 2026.
    """
    app = BACKEND.parent / "frontend/app"
    layout = (app / "layout.tsx").read_text(encoding="utf-8")
    assert "template: '%s | ASX Screener'" in layout, (
        "the title template changed; this rule needs rechecking")

    # Both quote styles, and any "| ASX Screener <Word>" tail.
    #
    # The first version of this pattern matched single-quoted titles ending in
    # exactly " | ASX Screener". Three pages escaped it and shipped: one used
    # DOUBLE quotes because its title contains an apostrophe ("the World's
    # Best..."), and two ended " | ASX Screener Education", a different suffix
    # the template then appended to again. The fix was right and the matcher
    # was too narrow, which is the same failure twice over.
    doubled = re.compile(
        r"\btitle:\s*(['\"]).*?\|\s*ASX Screener(?:\s+\w+)?\1")
    offenders = [p.relative_to(app).as_posix() for p in app.rglob("*.tsx")
                 if doubled.search(_executable_source(
                     p.read_text(encoding="utf-8")))]
    assert not offenders, (
        f"these pages append a suffix the layout already adds: {offenders}")


def test_the_title_matcher_covers_the_shapes_that_escaped_it():
    """Mutation control from the three titles that shipped duplicated."""
    doubled = re.compile(
        r"\btitle:\s*(['\"]).*?\|\s*ASX Screener(?:\s+\w+)?\1")
    escaped = [
        """  title: "Lessons from the World's Best Multibagger Investors | ASX Screener",""",
        """  title: 'Key Financial Ratios for ASX Investors | ASX Screener Education',""",
        """  title: 'How to Read ASX Company Announcements | ASX Screener Education',""",
        """  title: 'Data Freshness Policy | ASX Screener',""",
    ]
    missed = [s for s in escaped if not doubled.search(s)]
    assert not missed, f"still not matched: {missed}"

    # And it must not strike a title that merely mentions the brand inline,
    # which is legitimate: "One ASX Screener, Three Ways to Search".
    innocent = [
        "  title: 'One ASX Screener, Three Ways to Search',",
        "  title: 'How to Use ASX Screener Alpha Screens',",
        "  title: { default: 'Education Hub', template: '%s | ASX Screener' },",
    ]
    fired = [s for s in innocent if doubled.search(s)]
    assert not fired, f"false positives: {fired}"


def _public_prefixes() -> list[str]:
    src = (BACKEND.parent / "frontend/lib/public-routes.ts").read_text(
        encoding="utf-8")
    block = src[src.index("export const PUBLIC_PREFIXES"):
                src.index("export function isPublic")]
    return re.findall(r"'(/[a-z0-9/-]*)'", block)


def test_the_sitemap_advertises_only_reachable_pages():
    """A sitemap entry is a request to index a URL. Pointing a crawler at a
    page that answers with a login form is a contradiction, and on 2 Oct 2026
    the file did it 56 times out of 58.

    The two lists are kept separately on purpose -- a sitemap generated from
    the public set would make a URL vanish from search silently the moment
    someone gated a route. This asserts they agree, so it fails loudly.
    """
    sitemap = (BACKEND.parent / "frontend/app/sitemap.ts").read_text(
        encoding="utf-8")
    routes = sorted(set(re.findall(r"\$\{base\}(/[a-z0-9/-]*)`",
                                   _executable_source(sitemap))))
    assert routes, "no routes parsed; the sitemap changed shape"
    gated = [r for r in routes if not _is_public(r)]
    assert not gated, (
        f"the sitemap advertises pages that redirect to the login form: "
        f"{gated}. Open them, or remove them from the sitemap.")


def _sitemap_routes() -> list[str]:
    sitemap = (BACKEND.parent / "frontend/app/sitemap.ts").read_text(
        encoding="utf-8")
    return sorted(set(re.findall(r"\$\{base\}(/[a-z0-9/-]*)`",
                                 _executable_source(sitemap))))


def test_the_sitemap_advertises_nothing_behind_a_plan_gate():
    """The blind spot in the first version of this rule.

    Reachability was checked against ClientGuard only, so /glossary and
    /brokers passed — they are not redirected. Both wrap their entire page in
    <PlanGate required="pro">, so an anonymous visitor (and a crawler) gets
    "Sign in required — available on the Pro plan" and nothing else. Google
    was being asked to index a sign-in panel.

    A route is gated two ways: the router can refuse it, or the page can.
    Only the second was invisible here, which is why it survived a release
    that was explicitly about this contradiction.
    """
    app = BACKEND.parent / "frontend/app"
    offenders = []
    for route in _sitemap_routes():
        page = app / (route.lstrip("/") or ".") / "page.tsx"
        if not page.is_file():
            continue
        src = _executable_source(page.read_text(encoding="utf-8"))
        # Outermost element of the component's return -- a PlanGate wrapping
        # one widget inside an otherwise public page is not this defect.
        if re.search(r"return\s*\(\s*\n\s*<PlanGate", src):
            offenders.append(route)
    assert not offenders, (
        "the sitemap advertises pages whose entire content sits behind a plan "
        f"gate: {offenders}. Remove them, or render public content above the "
        f"gate.")


def test_the_plan_gate_detector_recognises_the_real_shape():
    """Mutation control, taken from app/brokers/page.tsx as it stood."""
    real = "export default function BrokersPage() {\n  return (\n    <PlanGate required=\"pro\" feature=\"Broker Compare\">\n"
    assert re.search(r"return\s*\(\s*\n\s*<PlanGate", real)
    partial = "  return (\n    <div>\n      <h1>Public</h1>\n      <PlanGate required=\"pro\">x</PlanGate>\n"
    assert not re.search(r"return\s*\(\s*\n\s*<PlanGate", partial), (
        "a gate around one widget must not condemn an otherwise public page")


def test_the_guard_and_the_sitemap_read_the_same_declaration():
    """Both consumers must import the shared module. A second copy of the
    prefix list is how these two drifted apart in the first place."""
    guard = (BACKEND.parent / "frontend/components/ClientGuard.tsx").read_text(
        encoding="utf-8")
    assert "@/lib/public-routes" in guard
    assert "const PUBLIC_PREFIXES" not in guard, (
        "ClientGuard holds its own copy of the public set again")


def _is_public(path: str) -> bool:
    return path == "/" or any(path.startswith(p) for p in _public_prefixes())


def test_opening_the_seo_landing_pages_does_not_open_the_product():
    """Three SEO pages live under /screener and are public by name. A prefix
    of '/screener' would have made the screener itself free, which is the
    opposite of the decision taken."""
    for product in ("/screener", "/market", "/scans", "/top5", "/news",
                    "/indices", "/funds", "/commodities", "/global-markets",
                    "/watchlist", "/portfolio", "/alerts", "/account",
                    "/admin", "/company/BHP", "/stock/BHP"):
        assert not _is_public(product), f"{product} became publicly reachable"

    for landing in ("/screener/asx-dividend-yield", "/screener/asx-market-cap",
                    "/screener/asx-moving-average", "/sectors/materials",
                    "/learn/roe-explained", "/resources", "/pricing",
                    "/data-freshness", "/contact", "/terms"):
        assert _is_public(landing), f"{landing} is still behind the login"


def test_a_layout_with_children_defines_a_title_template():
    """The half of the title fix that was missed first time round.

    Next resolves a plain `title: 'X'` in a layout to an ABSOLUTE title with
    no template, so child segments inherit nothing. app/learn/layout.tsx and
    app/screener/layout.tsx did that, which is why their 31 child pages had
    spelled the site suffix out by hand — they were compensating for a broken
    template chain, not duplicating one.

    Removing those suffixes without repairing the chain stripped the site name
    from five pages in production. Only `title.template` propagates.
    """
    app = BACKEND.parent / "frontend/app"
    offenders = []
    for layout in app.rglob("layout.tsx"):
        if layout.parent == app:
            continue                                   # the root defines it
        src = _executable_source(layout.read_text(encoding="utf-8"))
        if "title" not in src:
            continue
        has_children = any(p != layout.parent / "page.tsx"
                           for p in layout.parent.rglob("page.tsx"))
        if has_children and "template:" not in src:
            offenders.append(layout.relative_to(app).as_posix())
    assert not offenders, (
        "these layouts set a title but no template, so their child pages "
        f"inherit no site suffix: {offenders}")


def test_a_public_route_renders_without_waiting_for_auth():
    """ClientGuard returned a spinner whenever `loading` was true, and loading
    is true during server rendering -- so the server emitted a spinner for
    every route. The homepage shipped 68 KB of HTML with ~1,000 characters of
    visible text, all of it navbar and footer.

    A public route must short-circuit before that spinner.
    """
    src = _executable_source(
        (BACKEND.parent / "frontend/components/ClientGuard.tsx").read_text(
            encoding="utf-8"))
    body = src[src.index("export function ClientGuard"):]
    pub_return = body.index("if (pub) return")
    spinner = body.index("animate-spin")
    assert pub_return < spinner, (
        "the public short-circuit must come before the loading spinner, or "
        "public pages still server-render as a spinner")


def test_a_withheld_metric_explains_itself():
    """The API has always sent the reason; the UI threw it away.

    Every screener row carries `metric_states`: for each governed metric the
    engine declined to publish, a state, a cause and a sentence. BHP's P/E
    reads "price is quoted in AUD and earnings per share are stated in USD;
    the ratio has no unit until one side is converted" — and the landing page
    rendered a bare em dash, making the most defensible thing this product
    does indistinguishable from missing data.
    """
    page = _executable_source(
        (BACKEND.parent / "frontend/app/page.tsx").read_text(encoding="utf-8"))
    assert "MetricValue" in page, "the preview table renders bare dashes again"
    assert "metric_states" in page, "the sidecar is no longer read"
    for field in ("pe_ratio", "dividend_yield", "roe"):
        assert f'field="{field}"' in page, f"{field} is not explained"


def test_the_fields_endpoint_publishes_canonical_identity():
    """The backend is the only authority for canonical <-> physical identity.

    The sidecar is keyed canonically and rows are keyed by column; 8 of the 72
    governed metrics spell those differently. Before 2 Oct 2026 nothing
    published the mapping, so any client wanting to explain a withheld value
    had to reconstruct it — a second declaration of identity, which is exactly
    how ev_to_ebitda escaped assessment once already.
    """
    route = (BACKEND / "app/api/v1/routes/screener.py").read_text(
        encoding="utf-8")
    assert "governed_columns" in route, "the fields endpoint stopped publishing the map"
    assert '"canonical_metric"' in route, "field descriptors no longer carry canonical identity"
    assert '"governed"' in route

    # And it must be derived, not typed out.
    block = route[route.index("canonical_for_column = {"):
                  route.index("# Group fields by category")]
    assert "governed_columns(" in block, (
        "the mapping is hand-written rather than derived from the engine")
    assert "ev_ebitda" not in block, "an alias is spelled out by hand"


def test_the_frontend_never_redeclares_canonical_identity():
    """A client may consume canonical identity; it may never restate it.

    An alias table in the frontend would drift from the engine silently, and
    the drift would look exactly like a metric that simply has no explanation.
    """
    fe = BACKEND.parent / "frontend"
    for rel in ("lib/metric-states.ts", "components/MetricValue.tsx",
                "app/page.tsx", "app/screener/page.tsx",
                "app/company/[code]/CompanyTabs.tsx"):
        src = _executable_source((fe / rel).read_text(encoding="utf-8"))
        for alias in ("ev_ebitda", "dividend_per_share", "dividend_payout_ratio",
                      "net_income_cagr_3y", "eps_cagr_3y", "revenue_cagr_3y"):
            assert alias not in src, (
                f"{rel} names the canonical metric '{alias}' directly; it must "
                f"come from the API's governed_columns map")


def test_every_displayed_governed_metric_on_the_company_page_is_wired():
    """Wiring MetricRow was not the same as wiring the page.

    The Key Statistics strip — the most prominent card on /company/{code} —
    renders from an inline {label, value} array into plain divs, not through
    MetricRow. So after the first pass BHP's P/E, P/B, EV/EBITDA, PEG and
    Book Val/Sh showed unexplained dashes there while the feature was reported
    as delivered. It was found by looking at the rendered page: a plain dash
    and an explained dash are indistinguishable in a screenshot, which is
    exactly why this needs to be a test.

    Rule: any {label, value} entry whose value expression reads exactly one
    governed column must also name that column in `field`.
    """
    import sys as _sys
    _sys.path.insert(0, str(BACKEND))
    from compute.engine.metric_states import (                     # noqa: PLC0415
        GOVERNED_METRICS, LATEST_MODEL_VERSION)
    from compute.engine.universe_writer import column_for          # noqa: PLC0415
    governed = {column_for(m) for m in GOVERNED_METRICS[LATEST_MODEL_VERSION]}

    src = _executable_source(
        (BACKEND.parent / "frontend/app/company/[code]/CompanyTabs.tsx")
        .read_text(encoding="utf-8"))

    # An entry spans from its `label:` to the next one. Bounding it that way
    # needs no brace matching, which two earlier attempts got wrong against
    # real JS: a `(.+?)\},` capture ran past entries carrying `highlight:` and
    # mis-paired two metrics, and a lookahead on `}` stopped inside a template
    # literal's `${...}` and truncated an entry before its `field:`.
    starts = [m for m in re.finditer(r"\{\s*label:\s*'([^']+)',", src)]
    unwired = []
    for i, m in enumerate(starts):
        label = m.group(1)
        end = starts[i + 1].start() if i + 1 < len(starts) else len(src)
        span = src[m.start():end]
        if "value:" not in span:
            continue
        cols = {c for c in re.findall(r"\bo\.([a-z0-9_]+)", span)
                if c in governed}
        if len(cols) == 1 and "field:" not in span:
            unwired.append(f"{label} ({cols.pop()})")
    assert not unwired, (
        "these displayed governed metrics render an unexplained dash: "
        f"{unwired}")


def test_the_resolver_unit_tests_exist_and_cover_the_alias_case():
    """These run under node against the real module (npm run test:units).
    Asserted structurally here so the Python suite fails if they are deleted."""
    t = (BACKEND.parent / "frontend/lib/metric-states.test.mts")
    assert t.is_file(), "the resolver unit tests are gone"
    src = t.read_text(encoding="utf-8")
    assert "ev_to_ebitda surfaces the state stored under ev_ebitda" in src, (
        "the alias regression case was removed")
    for case in ("fails CLOSED", "applicable metric shows no explanation",
                 "plain dash", "not the enum"):
        assert case in src, f"missing absence-semantics case: {case}"

    pkg = (BACKEND.parent / "frontend/package.json").read_text(encoding="utf-8")
    assert "test:units" in pkg, "the unit tests are not runnable from package.json"


def test_every_explained_field_is_keyed_the_way_the_sidecar_is():
    """The trap this lookup walks into.

    The sidecar is keyed by CANONICAL metric name; a screener row is keyed by
    physical COLUMN. For 8 of the 72 governed metrics those differ —
    ev_ebitda/ev_to_ebitda, dividend_per_share/dps_ttm, and so on — and
    row_projection carries a comment saying this is "how ev_to_ebitda escaped
    assessment once already".

    A field passed to MetricValue is looked up in the sidecar directly, so it
    must be one whose two spellings agree. Wiring a mismatched metric would
    silently render an unexplained dash while the explanation sat in the
    payload under another name.
    """
    import sys as _sys
    _sys.path.insert(0, str(BACKEND))
    from compute.engine.metric_states import (                     # noqa: PLC0415
        GOVERNED_METRICS, LATEST_MODEL_VERSION)
    from compute.engine.universe_writer import column_for          # noqa: PLC0415

    governed = GOVERNED_METRICS[LATEST_MODEL_VERSION]
    page = _executable_source(
        (BACKEND.parent / "frontend/app/page.tsx").read_text(encoding="utf-8"))
    used = set(re.findall(r'<MetricValue\s+field="([a-z0-9_]+)"', page))
    assert used, "no explained metrics found on the landing page"

    for field in sorted(used):
        assert field in governed, (
            f"{field} is not a governed metric, so the sidecar will never "
            f"carry an entry for it")
        assert column_for(field) == field, (
            f"{field} is stored as column '{column_for(field)}'; a direct "
            f"sidecar lookup by column name will miss it. Map canonical to "
            f"column before wiring this metric.")


def test_the_explanation_reaches_the_markup_not_just_the_client():
    """A tooltip that only exists after hydration is not in the HTML a crawler
    or a screen reader receives. MetricValue must stay a server component with
    the reason on the element itself."""
    src = (BACKEND.parent / "frontend/components/MetricValue.tsx").read_text(
        encoding="utf-8")
    assert "'use client'" not in src, (
        "MetricValue became a client component; the explanation would then be "
        "absent from server-rendered HTML")
    body = _executable_source(src)
    assert "title=" in body and "aria-label=" in body, (
        "the reason must be carried by the element, not by a JS-only tooltip")
    # aria-label carries the state word plus the reason, so a screen reader
    # announces the dash as withheld rather than as an empty cell. (An earlier
    # version used a visually-hidden span; aria-label avoids the element being
    # announced twice.)
    assert "stateLabel(" in body, "the accessible name does not say it was withheld"


def test_an_unexplained_blank_claims_nothing():
    """A dash with no sidecar entry must not be labelled 'unavailable'.
    Asserting a cause we do not have would be the same error as inventing the
    number, in miniature."""
    src = _executable_source(
        (BACKEND.parent / "frontend/components/MetricValue.tsx").read_text(
            encoding="utf-8"))
    # The branch that renders a dash for anything other than 'explained'.
    guard = src[src.index("if (r.kind !== 'explained')"):]
    guard = guard[:guard.index("const text")]
    assert "—" in guard, "no plain-dash branch"
    for enum in ("unavailable", "not_meaningful", "insufficient_data"):
        assert enum not in guard.lower(), (
            f"the no-entry branch asserts '{enum}', a cause it was not given")

    # And the resolver must keep the two unexplained cases distinct, so a
    # failed map load is visible in diagnostics rather than silently equal to
    # "nothing was asserted".
    res = _executable_source(
        (BACKEND.parent / "frontend/lib/metric-states.ts").read_text(
            encoding="utf-8"))
    assert "'unmapped'" in res and "'plain'" in res


def test_a_trailing_return_is_not_labelled_as_pick_performance():
    """strategy.monthly_picks freezes u.return_3m at selection, so it is the
    stock's return in the three months BEFORE it was picked -- a reason it
    scored well, not an outcome.

    Displayed as "Avg 3M Ret" under a heading reading "Historical Picks", that
    is read as a track record by anyone who does not know the schema.
    """
    src = _executable_source(
        (BACKEND.parent / "frontend/app/top5/page.tsx").read_text(
            encoding="utf-8"))
    assert "Avg 3M Ret" not in src, (
        "a trailing return is labelled as though it were the picks' return")
    assert "prior 3m" in src.lower(), "the label no longer says it is prior"
    assert "not the performance of these picks" in src, (
        "the disclosure that this is not a track record was removed")
    assert "not a backtest" in src


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
