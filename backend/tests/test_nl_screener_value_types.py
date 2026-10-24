#!/usr/bin/env python
"""
A model's filter value must be the field's type before it reaches the driver
===========================================================================
From the production log, 22 October 2026:

    ERROR nl-screener DB error (sql ranking): could not convert string to
          float: 'low_52w'
    ERROR nl-screener DB error: could not convert string to float: 'low_52w'
    "POST /api/v1/ai/nl-screener HTTP/1.1" 500 Internal Server Error

Asked for something like "stocks trading near their 52-week low", the model
answered with a filter whose VALUE was a field name. The route checked the
field, the operator and the null case -- and never the value's type. The
string was bound to a numeric column and asyncpg objected, which the route
turned into a 500.

nl-screener had served nine requests in its life at that point:

    3 x 500      3 x 200      2 x 401 (a test)      1 x 422

Three of the five genuine customer attempts were that crash.

A model proposing a comparison between two FIELDS is asking for something
this screener cannot express. Dropping the criterion still answers the rest
of the question; forwarding it answers none of it. So the value is coerced
to the field's declared type or the criterion is dropped with a warning --
the same treatment already given to an unknown field, a bad operator and a
null.

Run:  python tests/test_nl_screener_value_types.py
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

for _k, _v in (("DATABASE_URL", "postgresql+asyncpg://unused/unused"),
               ("DATABASE_URL_SYNC", "postgresql://unused/unused"),
               ("JWT_SECRET", "test-only-not-a-secret")):
    os.environ.setdefault(_k, _v)

from app.api.v1.routes.ai import coerce_filter_value          # noqa: E402
from app.api.v1.routes.screener import ALLOWED_FIELDS         # noqa: E402


def _a_field_of(ftype: str) -> str:
    for name, meta in ALLOWED_FIELDS.items():
        if meta.get("type") == ftype:
            return name
    raise AssertionError(f"no field of type {ftype!r} in ALLOWED_FIELDS")


NUMBER = _a_field_of("number")
BOOLEAN = _a_field_of("boolean")


# ── The defect ──────────────────────────────────────────────────────────────

def test_a_field_name_as_a_value_is_refused():
    """The exact shape that produced the 500."""
    ok, _ = coerce_filter_value("price" if "price" in ALLOWED_FIELDS else NUMBER,
                                "low_52w")
    assert ok is False, (
        "a field name was accepted as a numeric value; it will be bound to a "
        "numeric column and the driver will raise, which the route serves "
        "as a 500")


def test_every_field_name_is_refused_as_a_numeric_value():
    """Not just low_52w. A model can name any field it has been shown."""
    refused = 0
    for name in list(ALLOWED_FIELDS)[:60]:
        ok, _ = coerce_filter_value(NUMBER, name)
        if not ok:
            refused += 1
    assert refused >= 55, (
        f"only {refused} of 60 field names were refused as numeric values; "
        f"a field name that parses as a number would still reach the driver")


# ── Real values must still work ─────────────────────────────────────────────

def test_numbers_are_accepted_in_the_shapes_a_model_emits():
    for raw, expected in ((5, 5), (4.5, 4.5), ("4.5", 4.5), ("  7 ", 7.0),
                          ("1,250", 1250.0), ("4.5%", 4.5), ("-3.2", -3.2)):
        ok, coerced = coerce_filter_value(NUMBER, raw)
        assert ok, f"{raw!r} was refused"
        assert float(coerced) == expected, f"{raw!r} -> {coerced!r}"


def test_booleans_accept_the_strings_a_model_emits():
    for raw in (True, "true", "True", "yes", "1"):
        ok, coerced = coerce_filter_value(BOOLEAN, raw)
        assert ok and coerced is True, f"{raw!r} -> {coerced!r}"
    for raw in (False, "false", "False", "no", "0"):
        ok, coerced = coerce_filter_value(BOOLEAN, raw)
        assert ok and coerced is False, f"{raw!r} -> {coerced!r}"


def test_a_boolean_is_not_a_number():
    """`True` is an int in Python. Binding it to a numeric column would
    compare against 1, which is a silent wrong answer rather than a crash --
    the worse of the two."""
    ok, _ = coerce_filter_value(NUMBER, True)
    assert ok is False, "True was accepted as a quantity"


def test_a_word_is_refused_for_a_boolean_field():
    ok, _ = coerce_filter_value(BOOLEAN, "low_52w")
    assert ok is False


def test_an_empty_string_is_refused():
    """It constrains nothing, so it only dilutes a preferred-score
    denominator."""
    for raw in ("", "   "):
        ok, _ = coerce_filter_value(NUMBER, raw)
        assert ok is False, f"{raw!r} was accepted"


# ── The premise ─────────────────────────────────────────────────────────────

def test_the_route_calls_the_validator():
    """A validator nothing reaches is a comment.

    The first version of this helper was nested inside the route, where it
    could not be imported and so could not be tested at all.
    """
    src = (BACKEND / "app" / "api" / "v1" / "routes" / "ai.py").read_text(
        encoding="utf-8")
    assert "coerce_filter_value(field, value)" in src, (
        "nl-screener no longer validates filter values against the field's "
        "type; a field name will reach the driver again")


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
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
