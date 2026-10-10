#!/usr/bin/env python
"""
A series whose provenance is unestablished publishes no figures
===============================================================
`AXJO` was published as "S&P/ASX 200 Accumulation — the total return version
... incorporating reinvestment of dividends ... the standard benchmark used
by Australian superannuation funds" and populated from `^AXJO`, the
**price-only** series. The producer comment admitted it: "accumulation —
same price series as ASX200 on Yahoo".

The codebase does not agree what the series is meant to be — ASX 200
accumulation in two places, All Ordinaries in three frontend comments — so
no replacement can be specified, let alone verified for return type,
currency, dividend treatment and date coverage. Containment is therefore
suppression, not substitution.

What is deliberately NOT asserted here
--------------------------------------
The size of the error. A price series understates a total-return series by
the dividend contribution, but that difference has not been measured against
a correct benchmark, and an unmeasured figure is exactly the kind of number
this whole effort exists to stop publishing.

Run:  python tests/test_unverified_series_is_contained.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.series_provenance import (                         # noqa: E402
    SUPPRESSED_FIELDS, UNVERIFIED_SERIES, is_unverified,
    suppress_if_unverified)

ROUTE = BACKEND / "app" / "api" / "v1" / "routes" / "indices_funds.py"


def _payload(code="AXJO"):
    return dict(index_code=code, display_name="x", price_date="2026-10-08",
                close_price=8000.0, return_1d=0.4, return_1w=1.1,
                return_1m=2.2, return_3m=3.3, return_6m=4.4, return_1y=9.1,
                return_ytd=7.7, high_52w=8200.0, low_52w=7100.0)


# ── Suppression ─────────────────────────────────────────────────────────────

def test_every_numeric_field_is_withheld():
    out = suppress_if_unverified("AXJO", _payload())
    leaked = [f for f in SUPPRESSED_FIELDS if out.get(f) is not None]
    assert not leaked, f"figures published for an unverified series: {leaked}"


def test_the_reason_is_published_so_it_is_not_mistaken_for_an_outage():
    out = suppress_if_unverified("AXJO", _payload())
    assert out["data_status"] == "series_provenance_unverified", (
        "suppression without a reason is indistinguishable from missing "
        "data, and missing data invites a retry")


def test_the_price_date_is_retained():
    """It says when the underlying rows stop -- what an investigator needs --
    and cannot be misread as a return."""
    assert suppress_if_unverified("AXJO", _payload())["price_date"] == "2026-10-08"


def test_a_sound_series_is_untouched():
    """Containment must not quietly blank the other nine indices."""
    p = _payload("ASX200")
    assert suppress_if_unverified("ASX200", p) == p
    assert "data_status" not in suppress_if_unverified("ASX200", p)


def test_the_code_match_is_case_insensitive():
    out = suppress_if_unverified("axjo", _payload("axjo"))
    assert out["close_price"] is None
    assert is_unverified("axjo") and is_unverified("AXJO")


def test_a_new_numeric_field_defaults_to_withheld_not_served():
    """SUPPRESSED_FIELDS is explicit, not inferred from the response model.

    If it were inferred, adding a field to IndexPrice would start publishing
    it for a suppressed series the moment someone added it.
    """
    schema = (BACKEND / "app" / "schemas" / "indices_funds.py").read_text(
        encoding="utf-8")
    block = schema[schema.index("class IndexPrice"):schema.index("class IndicesResponse")]
    numeric = set(re.findall(r"^\s{4}(\w+):\s*Optional\[float\]", block, re.M))
    missing = numeric - set(SUPPRESSED_FIELDS)
    assert not missing, (
        f"IndexPrice publishes numeric fields the suppression list does not "
        f"cover, so an unverified series would serve them: {sorted(missing)}")


# ── Every consumer of the series ────────────────────────────────────────────

def test_the_producer_no_longer_fetches_it():
    """New rows must not accrue under a provenance we cannot support."""
    src = (BACKEND / "compute" / "engine" / "index_prices.py").read_text(
        encoding="utf-8")
    block = src[src.index("TICKER_MAP"):src.index("# ── Return computation")]
    live = re.findall(r'^\s{4}"(\w+)":\s*"\^', block, re.M)
    assert "AXJO" not in live, (
        "index_prices still fetches AXJO, so rows keep accruing under an "
        "unverified provenance")
    assert "ASX200" in live, "the control index was removed too"


def test_all_three_endpoints_apply_containment():
    """List, detail and history each consume the series separately.

    Covering two of three would leave the third publishing the figures the
    other two withhold.
    """
    src = ROUTE.read_text(encoding="utf-8")
    assert src.count("suppress_if_unverified(") >= 2, (
        "the list and detail endpoints do not both suppress")
    assert "if code_u in UNVERIFIED_SERIES:" in src, (
        "the history endpoint does not check, so a chart would render the "
        "points that the list and detail endpoints withhold -- and a chart "
        "is harder to caveat than a number")


def test_the_published_description_no_longer_claims_total_return():
    """The description was the claim the figures could not support."""
    src = ROUTE.read_text(encoding="utf-8")
    block = src[src.index('"AXJO": {'):]
    block = block[:block.index("},")]
    lowered = block.lower()
    assert "unavailable" in lowered, (
        "AXJO is not marked unavailable to the reader")
    for claim in ("more accurate measure", "standard benchmark used by"):
        assert claim not in lowered, (
            f"the description still asserts {claim!r} for a withheld series")


def test_the_finding_is_recorded():
    doc = BACKEND.parent / "docs" / \
        "finding_2026-10-09_axjo_accumulation_is_price_series.md"
    assert doc.exists(), "the containment has no written finding behind it"


# ── The reason reaches every user, not just a mouse ─────────────────────────

FRONTEND = BACKEND.parent / "frontend"
LIST_PAGE = FRONTEND / "app" / "indices" / "page.tsx"
DETAIL_PAGE = FRONTEND / "app" / "indices" / "[code]" / "IndexDetailContent.tsx"


def code_only(src: str) -> str:
    """Strip comments before scanning.

    Twice now a check has failed on the comment explaining the very decision
    it was verifying -- here, a `title=` inside the note saying why there is
    no title tooltip. A scanner that reads prose tests the documentation, not
    the code. See [[engineering-rule-structural-not-textual]].
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def test_the_list_states_the_reason_in_visible_text():
    """Not a title= tooltip.

    A tooltip is unreachable by keyboard and never appears on touch, so on a
    phone the badge would read UNAVAILABLE with no way to discover why. The
    first version of this badge did exactly that.
    """
    src = code_only(LIST_PAGE.read_text(encoding="utf-8"))
    block = src[src.index("idx.data_status"):]
    block = block[:block.index("screenerHref")]
    assert "could not be verified" in block, (
        "the list does not state the reason in rendered text")
    assert "title=" not in block, (
        "the reason is carried on a title attribute, which keyboard and "
        "touch users never see")


def test_the_detail_page_states_it_too():
    """Under suppression the price header is skipped entirely, so without an
    explicit block the page reads as a loading failure."""
    src = DETAIL_PAGE.read_text(encoding="utf-8")
    assert "p?.data_status" in src, (
        "the detail page never checks data_status, so a withheld series is "
        "indistinguishable from a page that failed to load")
    assert "Figures unavailable" in src


def test_the_chart_does_not_say_the_data_is_coming():
    """"No price history available YET" implies it is on its way. For a
    withheld series it is not, and that distinction is the containment."""
    src = DETAIL_PAGE.read_text(encoding="utf-8")
    assert "unavailable?: boolean" in src, (
        "the chart cannot tell a withheld series from an empty one")
    assert "Chart unavailable." in src
    assert "unavailable={!!p?.data_status}" in src, (
        "the chart is never told the series is withheld")


def test_verified_indices_are_untouched_in_the_ui():
    """Containment must be conditional, not global.

    Every unavailable affordance has to sit behind a data_status check, or
    ASX200 and the other verified indices would render the same warning.
    """
    for page in (LIST_PAGE, DETAIL_PAGE):
        src = code_only(page.read_text(encoding="utf-8"))
        for marker in ("UNAVAILABLE", "Figures unavailable", "Chart unavailable."):
            idx = src.find(marker)
            if idx == -1:
                continue
            preceding = src[max(0, idx - 700):idx]
            # `unavailable` counts: PerformanceChart receives the flag as a
            # prop rather than reading data_status itself, which is the right
            # shape -- the component should not know about provenance, only
            # that this series is withheld. The call site is checked below.
            assert "data_status" in preceding or "unavailable" in preceding, (
                f"{page.name}: {marker!r} is rendered unguarded, so verified "
                f"indices would show it too")
    detail = code_only(DETAIL_PAGE.read_text(encoding="utf-8"))
    assert "unavailable={!!p?.data_status}" in detail, (
        "the chart's unavailable prop is not derived from data_status, so it "
        "could be set for a verified index")


def test_the_suppression_set_is_not_silently_emptied():
    """Mutation control.

    Every test above passes vacuously if UNVERIFIED_SERIES is empty -- the
    suppression helper becomes an identity function and nothing fails.
    """
    assert UNVERIFIED_SERIES, (
        "UNVERIFIED_SERIES is empty, so every containment assertion in this "
        "file is vacuous")
    assert "AXJO" in UNVERIFIED_SERIES


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
            except Exception as exc:                             # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
