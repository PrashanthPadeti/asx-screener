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


def test_the_offer_deadline_is_declared_once():
    """The landing page and the pricing page both advertised 'offer ends
    September 2026' as prose, in five places. The deadline passed on 30 Sep
    and the site kept advertising it, because nothing connected the copies."""
    offer = BACKEND.parent / "frontend/lib/offer.ts"
    assert offer.is_file(), "the shared deadline module is gone"
    for page in ("frontend/app/page.tsx", "frontend/app/pricing/page.tsx"):
        src = _executable_source(
            (BACKEND.parent / page).read_text(encoding="utf-8"))
        assert not re.search(r"(January|February|March|April|May|June|July|"
                             r"August|September|October|November|December)\s+20\d\d",
                             src), f"a literal month/year deadline is back in {page}"
        assert "OFFER_ENDS" in src, f"{page} no longer uses the shared deadline"


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
