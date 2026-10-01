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
)


#: A scale claim stated as a literal. `(?:more\s+)?` matters: the landing page
#: said "and 40+ more metrics", and a pattern demanding the noun immediately
#: after the number walked straight past it.
_SCALE_CLAIM = re.compile(
    r"\b\d{1,3},?\d{3}\+?\s*(?:ASX|stocks|companies)"        # 2,000+ ASX
    r"|\b\d{2,4}\+\s*(?:more\s+)?(?:fields|metrics)"         # 235+ fields
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
