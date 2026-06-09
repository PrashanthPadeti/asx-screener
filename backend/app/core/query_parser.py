"""
ASX Screener — SQL-Like Query Parser
======================================
Converts a human-readable WHERE expression like:

    roe > 10 AND (roce > 10 OR roic > 10)

into a parameterized SQL WHERE fragment safe for direct use in screener.universe queries.

Security model:
  - All field names resolved through ALLOWED_FIELDS whitelist — no raw column names
  - All values become named parameters (:qp0, :qp1, ...) — zero string interpolation
  - Operators validated against a fixed whitelist

Supported syntax:
  field_name  operator  number   [ AND | OR  field_name operator number ]
  field_name  operator  number   AND ( field_name operator number OR ... )

  Operators:  >  >=  <  <=  =  !=  <>
  Connectors: AND  OR  (case-insensitive)
  Grouping:   ( ... )
  Values:     integers or decimals (e.g. 10, 15.5, -5)

Field names are matched case-insensitively against a combined alias map that
includes all ALLOWED_FIELDS keys plus human-readable aliases (see EXTRA_ALIASES).

Usage:
    from app.core.query_parser import parse_query, get_field_reference, QueryParseError

    try:
        where_sql, params = parse_query("roe > 10 AND (roce > 10 OR roic > 10)",
                                         ALLOWED_FIELDS)
    except QueryParseError as exc:
        raise HTTPException(422, str(exc))
"""

from __future__ import annotations

import re
from typing import Any


# ── Exception ─────────────────────────────────────────────────────────────────

class QueryParseError(Exception):
    """Raised when the query text cannot be parsed into valid SQL."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Field Alias Map ───────────────────────────────────────────────────────────
# Human-readable names, abbreviations and phrase variants → ALLOWED_FIELDS key.
# The parser also auto-accepts every ALLOWED_FIELDS key directly (layer 1).

EXTRA_ALIASES: dict[str, str] = {

    # ── Profitability ──────────────────────────────────────────────────────────
    "return on equity":                              "roe",
    "return on capital employed":                    "roce",
    "return on invested capital":                    "roic",
    "opm":                                           "operating_margin",
    "operating margin":                              "operating_margin",
    "operating profit margin":                       "operating_margin",
    "net margin":                                    "net_margin",
    "gross margin":                                  "gross_margin",
    "ebitda margin":                                 "ebitda_margin",
    "return on assets":                              "roa",

    # ── OPM variants with time period ─────────────────────────────────────────
    "opm 3y":                                        "avg_operating_margin_3y",
    "opm 3yr":                                       "avg_operating_margin_3y",
    "opm 3year":                                     "avg_operating_margin_3y",
    "opm 3years":                                    "avg_operating_margin_3y",
    "average opm 3y":                                "avg_operating_margin_3y",
    "average operating margin 3y":                   "avg_operating_margin_3y",
    "average operating margin 3year":                "avg_operating_margin_3y",
    "average operating margin 3years":               "avg_operating_margin_3y",
    "avg opm 3y":                                    "avg_operating_margin_3y",
    "avg operating margin 3y":                       "avg_operating_margin_3y",
    "opm 5y":                                        "avg_operating_margin_5y",
    "opm 5yr":                                       "avg_operating_margin_5y",
    "opm 5year":                                     "avg_operating_margin_5y",
    "opm 5years":                                    "avg_operating_margin_5y",
    "average opm 5y":                                "avg_operating_margin_5y",
    "average operating margin 5y":                   "avg_operating_margin_5y",
    "average operating margin 5year":                "avg_operating_margin_5y",
    "average operating margin 5years":               "avg_operating_margin_5y",
    "avg opm 5y":                                    "avg_operating_margin_5y",
    "avg operating margin 5y":                       "avg_operating_margin_5y",

    # ── Valuation ─────────────────────────────────────────────────────────────
    "pe":                                            "pe_ratio",
    "p/e":                                           "pe_ratio",
    "p e":                                           "pe_ratio",
    "pe ratio":                                      "pe_ratio",
    "price to earning":                              "pe_ratio",
    "price to earnings":                             "pe_ratio",
    "price earnings ratio":                          "pe_ratio",
    "p/b":                                           "price_to_book",
    "pb":                                            "price_to_book",
    "price to book":                                 "price_to_book",
    "p/s":                                           "price_to_sales",
    "ps":                                            "price_to_sales",
    "price to sales":                                "price_to_sales",
    "ev ebitda":                                     "ev_to_ebitda",
    "ev/ebitda":                                     "ev_to_ebitda",
    "peg":                                           "peg_ratio",
    "fcf yield":                                     "fcf_yield",
    "free cash flow yield":                          "fcf_yield",
    "market cap":                                    "market_cap",
    "market capitalisation":                         "market_cap",
    "market capitalization":                         "market_cap",

    # ── Growth — Sales / Revenue ───────────────────────────────────────────────
    "sales growth":                                  "revenue_growth_1y",
    "revenue growth":                                "revenue_growth_1y",
    "sales growth 1y":                               "revenue_growth_1y",
    "sales growth 1yr":                              "revenue_growth_1y",
    "sales growth 1year":                            "revenue_growth_1y",
    "sales growth 1years":                           "revenue_growth_1y",
    "revenue growth 1y":                             "revenue_growth_1y",
    "revenue growth 1year":                          "revenue_growth_1y",

    "sales growth 3y":                               "revenue_growth_3y_cagr",
    "sales growth 3yr":                              "revenue_growth_3y_cagr",
    "sales growth 3year":                            "revenue_growth_3y_cagr",
    "sales growth 3years":                           "revenue_growth_3y_cagr",
    "revenue cagr 3y":                               "revenue_growth_3y_cagr",
    "revenue growth 3y":                             "revenue_growth_3y_cagr",
    "revenue growth 3year":                          "revenue_growth_3y_cagr",
    "revenue growth 3years":                         "revenue_growth_3y_cagr",

    "sales growth 5y":                               "revenue_cagr_5y",
    "sales growth 5yr":                              "revenue_cagr_5y",
    "sales growth 5year":                            "revenue_cagr_5y",
    "sales growth 5years":                           "revenue_cagr_5y",
    "revenue cagr 5y":                               "revenue_cagr_5y",
    "revenue growth 5y":                             "revenue_cagr_5y",
    "revenue growth 5year":                          "revenue_cagr_5y",
    "revenue growth 5years":                         "revenue_cagr_5y",

    "sales growth 7y":                               "revenue_cagr_7y",
    "sales growth 7yr":                              "revenue_cagr_7y",
    "sales growth 7year":                            "revenue_cagr_7y",
    "sales growth 7years":                           "revenue_cagr_7y",
    "revenue cagr 7y":                               "revenue_cagr_7y",
    "revenue growth 7y":                             "revenue_cagr_7y",
    "revenue growth 7year":                          "revenue_cagr_7y",
    "revenue growth 7years":                         "revenue_cagr_7y",

    "sales growth 10y":                              "revenue_cagr_10y",
    "sales growth 10yr":                             "revenue_cagr_10y",
    "sales growth 10year":                           "revenue_cagr_10y",
    "sales growth 10years":                          "revenue_cagr_10y",
    "revenue cagr 10y":                              "revenue_cagr_10y",
    "revenue growth 10y":                            "revenue_cagr_10y",
    "revenue growth 10year":                         "revenue_cagr_10y",
    "revenue growth 10years":                        "revenue_cagr_10y",

    # ── Growth — Earnings / Profit ─────────────────────────────────────────────
    "profit growth":                                 "earnings_growth_1y",
    "earnings growth":                               "earnings_growth_1y",
    "profit growth 1y":                              "earnings_growth_1y",
    "earnings growth 1y":                            "earnings_growth_1y",
    "profit growth 1year":                           "earnings_growth_1y",
    "earnings growth 1year":                         "earnings_growth_1y",

    "profit growth 3y":                              "earnings_growth_3y_cagr",
    "profit growth 3yr":                             "earnings_growth_3y_cagr",
    "profit growth 3year":                           "earnings_growth_3y_cagr",
    "profit growth 3years":                          "earnings_growth_3y_cagr",
    "earnings cagr 3y":                              "earnings_growth_3y_cagr",
    "earnings growth 3y":                            "earnings_growth_3y_cagr",
    "earnings growth 3year":                         "earnings_growth_3y_cagr",
    "earnings growth 3years":                        "earnings_growth_3y_cagr",

    "profit growth 5y":                              "eps_cagr_5y",
    "profit growth 5yr":                             "eps_cagr_5y",
    "profit growth 5year":                           "eps_cagr_5y",
    "profit growth 5years":                          "eps_cagr_5y",
    "earnings cagr 5y":                              "eps_cagr_5y",
    "earnings growth 5y":                            "eps_cagr_5y",
    "earnings growth 5year":                         "eps_cagr_5y",
    "earnings growth 5years":                        "eps_cagr_5y",

    # ── EBITDA Growth ─────────────────────────────────────────────────────────
    "ebitda growth":                                 "ebitda_growth_1y",
    "ebitda growth 1y":                              "ebitda_growth_1y",
    "ebitda cagr 3y":                                "ebitda_cagr_3y",
    "ebitda cagr 5y":                                "ebitda_cagr_5y",

    # ── FCF Growth ────────────────────────────────────────────────────────────
    "free cash flow growth":                         "fcf_growth_1y",
    "fcf growth":                                    "fcf_growth_1y",
    "fcf growth 1y":                                 "fcf_growth_1y",
    "fcf cagr 3y":                                   "fcf_cagr_3y",
    "fcf cagr 5y":                                   "fcf_cagr_5y",

    # ── Quality — Rolling Averages ─────────────────────────────────────────────
    "avg roe 3y":                                    "avg_roe_3y",
    "avg roe 3year":                                 "avg_roe_3y",
    "avg roe 3years":                                "avg_roe_3y",
    "average roe 3y":                                "avg_roe_3y",
    "average roe 3year":                             "avg_roe_3y",
    "average roe 3years":                            "avg_roe_3y",
    "average return on equity 3y":                   "avg_roe_3y",
    "average return on equity 3year":                "avg_roe_3y",
    "average return on equity 3years":               "avg_roe_3y",

    "avg roe 5y":                                    "avg_roe_5y",
    "avg roe 5year":                                 "avg_roe_5y",
    "avg roe 5years":                                "avg_roe_5y",
    "average roe 5y":                                "avg_roe_5y",
    "average roe 5year":                             "avg_roe_5y",
    "average roe 5years":                            "avg_roe_5y",
    "average return on equity 5y":                   "avg_roe_5y",
    "average return on equity 5year":                "avg_roe_5y",
    "average return on equity 5years":               "avg_roe_5y",

    "avg roa 3y":                                    "avg_roa_3y",
    "average roa 3y":                                "avg_roa_3y",
    "avg roa 5y":                                    "avg_roa_5y",
    "average roa 5y":                                "avg_roa_5y",

    "avg roce 3y":                                   "avg_roce_3y",
    "avg roce 3year":                                "avg_roce_3y",
    "avg roce 3years":                               "avg_roce_3y",
    "average roce 3y":                               "avg_roce_3y",
    "average roce 3year":                            "avg_roce_3y",
    "average roce 3years":                           "avg_roce_3y",
    "average return on capital employed 3y":         "avg_roce_3y",
    "average return on capital employed 3year":      "avg_roce_3y",
    "average return on capital employed 3years":     "avg_roce_3y",

    "avg roce 5y":                                   "avg_roce_5y",
    "avg roce 5year":                                "avg_roce_5y",
    "avg roce 5years":                               "avg_roce_5y",
    "average roce 5y":                               "avg_roce_5y",
    "average roce 5year":                            "avg_roce_5y",
    "average roce 5years":                           "avg_roce_5y",
    "average return on capital employed 5y":         "avg_roce_5y",
    "average return on capital employed 5year":      "avg_roce_5y",
    "average return on capital employed 5years":     "avg_roce_5y",

    "avg roic 3y":                                   "avg_roic_3y",
    "average roic 3y":                               "avg_roic_3y",
    "avg roic 5y":                                   "avg_roic_5y",
    "average roic 5y":                               "avg_roic_5y",

    "avg gross margin 3y":                           "avg_gross_margin_3y",
    "average gross margin 3y":                       "avg_gross_margin_3y",
    "avg gross margin 5y":                           "avg_gross_margin_5y",
    "average gross margin 5y":                       "avg_gross_margin_5y",
    "avg ebitda margin 3y":                          "avg_ebitda_margin_3y",
    "average ebitda margin 3y":                      "avg_ebitda_margin_3y",
    "avg ebitda margin 5y":                          "avg_ebitda_margin_5y",
    "average ebitda margin 5y":                      "avg_ebitda_margin_5y",
    "avg net margin 3y":                             "avg_net_margin_3y",
    "average net margin 3y":                         "avg_net_margin_3y",
    "avg net margin 5y":                             "avg_net_margin_5y",
    "average net margin 5y":                         "avg_net_margin_5y",

    # ── Dividends ─────────────────────────────────────────────────────────────
    "dividend yield":                                "dividend_yield",
    "div yield":                                     "dividend_yield",
    "grossed up yield":                              "grossed_up_yield",
    "grossed-up yield":                              "grossed_up_yield",
    "franking":                                      "franking_pct",
    "franking pct":                                  "franking_pct",
    "franking percent":                              "franking_pct",
    "fully franked":                                 "franking_pct",
    "payout ratio":                                  "payout_ratio",

    # ── Financial Strength ────────────────────────────────────────────────────
    "debt equity":                                   "debt_to_equity",
    "debt to equity":                                "debt_to_equity",
    "d/e":                                           "debt_to_equity",
    "debt/equity":                                   "debt_to_equity",
    "current ratio":                                 "current_ratio",
    "interest coverage":                             "interest_coverage",
    "net debt ebitda":                               "net_debt_to_ebitda",
    "net debt/ebitda":                               "net_debt_to_ebitda",
    "debt to assets":                                "debt_to_assets",
    "debt/assets":                                   "debt_to_assets",

    # ── Quality Scores ────────────────────────────────────────────────────────
    "piotroski":                                     "piotroski_f_score",
    "f score":                                       "piotroski_f_score",
    "f-score":                                       "piotroski_f_score",
    "piotroski score":                               "piotroski_f_score",
    "altman z":                                      "altman_z_score",
    "z score":                                       "altman_z_score",
    "z-score":                                       "altman_z_score",
    "altman":                                        "altman_z_score",

    # ── Returns ───────────────────────────────────────────────────────────────
    "return 1w":                                     "return_1w",
    "return 1m":                                     "return_1m",
    "return 3m":                                     "return_3m",
    "return 6m":                                     "return_6m",
    "return 1y":                                     "return_1y",
    "return ytd":                                    "return_ytd",
    "return 3y":                                     "return_3y",
    "return 5y":                                     "return_5y",
    "1 week return":                                 "return_1w",
    "1 month return":                                "return_1m",
    "3 month return":                                "return_3m",
    "6 month return":                                "return_6m",
    "1 year return":                                 "return_1y",
    "3 year return":                                 "return_3y",
    "5 year return":                                 "return_5y",

    # ── Technicals ────────────────────────────────────────────────────────────
    "rsi":                                           "rsi_14",
    "rsi 14":                                        "rsi_14",
    "beta":                                          "beta_1y",
    "beta 1y":                                       "beta_1y",
    "sharpe":                                        "sharpe_1y",
    "sharpe ratio":                                  "sharpe_1y",
    "volatility":                                    "volatility_20d",
    "volatility 20d":                                "volatility_20d",
    "volatility 60d":                                "volatility_60d",
    "adx":                                           "adx_14",

    # ── Price ─────────────────────────────────────────────────────────────────
    "price":                                         "price",
    "share price":                                   "price",
    "volume":                                        "volume",
    "52w high":                                      "high_52w",
    "52 week high":                                  "high_52w",
    "52w low":                                       "low_52w",
    "52 week low":                                   "low_52w",
}


def _build_alias_map(allowed_fields: dict) -> dict[str, str]:
    """
    Build the full alias → field_key lookup:
      Layer 1: every ALLOWED_FIELDS key maps to itself (e.g. "roe" → "roe")
      Layer 2: EXTRA_ALIASES (human phrases, abbreviations)
    """
    alias_map: dict[str, str] = {}

    # Layer 1: direct field key usage
    for key in allowed_fields:
        alias_map[key.lower()] = key

    # Layer 2: extra aliases (only for fields that actually exist)
    for alias, field_key in EXTRA_ALIASES.items():
        if field_key in allowed_fields:
            alias_map[alias.lower()] = field_key

    return alias_map


# ── Tokenizer ─────────────────────────────────────────────────────────────────

TT_OP     = "OP"      # >=, <=, !=, <>, >, <, =
TT_LPAREN = "LPAREN"  # (
TT_RPAREN = "RPAREN"  # )
TT_NUMBER = "NUMBER"  # integer or decimal (may be negative)
TT_WORD   = "WORD"    # identifier / keyword token

_TOKEN_RE = re.compile(
    r"""
    \s+                                   # skip whitespace
    | (>=|<=|!=|<>|>|<|=)                # comparison operators
    | (\()                                # left paren
    | (\))                                # right paren
    | (-?\d+(?:\.\d+)?)                   # numbers (incl. negative)
    | ([A-Za-z_][A-Za-z0-9_\-\./]*)      # words / identifiers
    """,
    re.VERBOSE,
)

_KEYWORDS = frozenset({"AND", "OR"})


class _Token:
    __slots__ = ("type", "value")

    def __init__(self, ttype: str, value: str):
        self.type  = ttype
        self.value = value

    def __repr__(self) -> str:
        return f"Token({self.type!r}, {self.value!r})"


def _tokenize(text: str) -> list[_Token]:
    """Lex the query into a flat token list, skipping whitespace."""
    tokens: list[_Token] = []
    for m in _TOKEN_RE.finditer(text):
        op, lp, rp, num, word = (
            m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        )
        if op is not None:
            tokens.append(_Token(TT_OP, op))
        elif lp is not None:
            tokens.append(_Token(TT_LPAREN, "("))
        elif rp is not None:
            tokens.append(_Token(TT_RPAREN, ")"))
        elif num is not None:
            tokens.append(_Token(TT_NUMBER, num))
        elif word is not None:
            tokens.append(_Token(TT_WORD, word))
        # whitespace matched first group → all groups None → skip
    return tokens


# ── AST Node classes ──────────────────────────────────────────────────────────

class _ConditionNode:
    """Leaf: (sql_col) op :param"""

    def __init__(self, col: str, op: str, value: float):
        self.col   = col
        self.op    = op
        self.value = value

    def to_sql(self, params: dict, counter: list) -> str:
        key = f"qp{counter[0]}"
        params[key] = self.value
        counter[0] += 1
        return f"({self.col}) {self.op} :{key}"


class _AndNode:
    def __init__(self, left, right):
        self.left  = left
        self.right = right

    def to_sql(self, params: dict, counter: list) -> str:
        l = self.left.to_sql(params, counter)
        r = self.right.to_sql(params, counter)
        return f"({l}) AND ({r})"


class _OrNode:
    def __init__(self, left, right):
        self.left  = left
        self.right = right

    def to_sql(self, params: dict, counter: list) -> str:
        l = self.left.to_sql(params, counter)
        r = self.right.to_sql(params, counter)
        return f"({l}) OR ({r})"


# ── Recursive Descent Parser ──────────────────────────────────────────────────

_OP_SQL: dict[str, str] = {
    ">":  ">",
    ">=": ">=",
    "<":  "<",
    "<=": "<=",
    "=":  "=",
    "!=": "!=",
    "<>": "!=",
}


class _Parser:
    def __init__(
        self,
        tokens: list[_Token],
        alias_map: dict[str, str],
        allowed_fields: dict,
    ):
        self.tokens         = tokens
        self.pos            = 0
        self.alias_map      = alias_map
        self.allowed_fields = allowed_fields

    # ── helpers ───────────────────────────────────────────────────────────────

    def _eof(self) -> bool:
        return self.pos >= len(self.tokens)

    def _peek(self) -> _Token | None:
        return self.tokens[self.pos] if not self._eof() else None

    def _consume(self) -> _Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _peek_keyword(self, kw: str) -> bool:
        tok = self._peek()
        return (
            tok is not None
            and tok.type == TT_WORD
            and tok.value.upper() == kw.upper()
        )

    # ── grammar: OR > AND > atom > condition ──────────────────────────────────

    def parse(self):
        node = self._parse_or()
        if not self._eof():
            remaining = " ".join(t.value for t in self.tokens[self.pos:self.pos + 5])
            raise QueryParseError(
                f"Unexpected text near end of query: '{remaining}'. "
                "Check for missing AND/OR between conditions."
            )
        return node

    def _parse_or(self):
        left = self._parse_and()
        while self._peek_keyword("OR"):
            self._consume()
            right = self._parse_and()
            left = _OrNode(left, right)
        return left

    def _parse_and(self):
        left = self._parse_atom()
        while self._peek_keyword("AND"):
            self._consume()
            right = self._parse_atom()
            left = _AndNode(left, right)
        return left

    def _parse_atom(self):
        tok = self._peek()
        if tok is None:
            raise QueryParseError(
                "Unexpected end of query — expected a field name or '('"
            )
        if tok.type == TT_LPAREN:
            self._consume()             # consume "("
            node = self._parse_or()
            if self._eof() or self._peek().type != TT_RPAREN:
                raise QueryParseError("Missing closing parenthesis ')'")
            self._consume()             # consume ")"
            return node
        return self._parse_condition()

    def _parse_condition(self):
        # ── Collect word tokens until hitting an operator, paren, OR/AND ──────
        words: list[str] = []
        while not self._eof():
            tok = self._peek()
            if tok.type == TT_OP:
                break
            if tok.type in (TT_LPAREN, TT_RPAREN, TT_NUMBER):
                break
            if tok.type == TT_WORD and tok.value.upper() in _KEYWORDS:
                break
            if tok.type == TT_WORD:
                words.append(self._consume().value)
            else:
                break

        if not words:
            ctx = self._peek().value if not self._eof() else "end of query"
            raise QueryParseError(
                f"Expected a field name but got '{ctx}'. "
                "Make sure every condition follows the pattern: field_name operator value"
            )

        raw_phrase = " ".join(words)

        # ── Greedy field resolution (longest match wins) ──────────────────────
        field_key: str | None = None
        matched_count = 0

        for length in range(len(words), 0, -1):
            candidate = " ".join(words[:length]).lower()
            if candidate in self.alias_map:
                field_key     = self.alias_map[candidate]
                matched_count = length
                break

        if field_key is None:
            raise QueryParseError(
                f"Field not recognized: '{raw_phrase}'. "
                "Use a field key (e.g. 'roe', 'revenue_cagr_5y') or an alias. "
                "See the Field Reference panel for all available fields."
            )

        # If greedy matched fewer words than consumed, the extra words are junk
        if matched_count < len(words):
            extra = " ".join(words[matched_count:])
            raise QueryParseError(
                f"Unexpected text '{extra}' after field name "
                f"'{' '.join(words[:matched_count])}'. "
                "Did you miss an operator?"
            )

        field_info = self.allowed_fields[field_key]

        # ── Operator ──────────────────────────────────────────────────────────
        if self._eof() or self._peek().type != TT_OP:
            got = self._peek().value if not self._eof() else "end of query"
            raise QueryParseError(
                f"Expected an operator (>, >=, <, <=, =, !=) after '{raw_phrase}', "
                f"got '{got}'"
            )
        op_tok = self._consume()
        sql_op = _OP_SQL.get(op_tok.value)
        if sql_op is None:
            raise QueryParseError(
                f"Unknown operator '{op_tok.value}'. "
                "Supported operators: >  >=  <  <=  =  !=  <>"
            )

        # ── Value ─────────────────────────────────────────────────────────────
        if self._eof() or self._peek().type != TT_NUMBER:
            got = self._peek().value if not self._eof() else "end of query"
            raise QueryParseError(
                f"Expected a numeric value after '{raw_phrase} {op_tok.value}', "
                f"got '{got}'. Only numeric conditions are supported."
            )
        val_tok = self._consume()
        try:
            raw_value = float(val_tok.value)
        except ValueError:
            raise QueryParseError(f"Invalid number: '{val_tok.value}'")

        # Apply scale factor (user types 10 meaning 10%; DB stores 0.10)
        scale    = field_info.get("scale", 1.0)
        db_value = raw_value * scale

        return _ConditionNode(field_info["col"], sql_op, db_value)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_query(
    query_text: str,
    allowed_fields: dict,
) -> tuple[str, dict[str, Any]]:
    """
    Parse a SQL-like query string into a parameterized SQL WHERE fragment.

    Parameters
    ----------
    query_text:
        Human-readable query, e.g. ``"roe > 10 AND (roce > 10 OR roic > 10)"``
    allowed_fields:
        The ALLOWED_FIELDS dict from screener.py — used for field resolution
        and scale factor lookup.

    Returns
    -------
    (where_fragment, params)
        ``where_fragment`` is a SQL string with named parameters ``(:qp0, :qp1, …)``.
        ``params`` is the corresponding ``{key: value}`` dict ready for
        ``db.execute(text(sql), params)``.

    Raises
    ------
    QueryParseError
        On unknown fields, invalid operators, syntax errors, or empty input.
    """
    if not query_text or not query_text.strip():
        raise QueryParseError("Query cannot be empty")

    alias_map = _build_alias_map(allowed_fields)
    tokens    = _tokenize(query_text)

    if not tokens:
        raise QueryParseError("Query contains no recognizable tokens")

    parser = _Parser(tokens, alias_map, allowed_fields)
    root   = parser.parse()

    params:  dict[str, Any] = {}
    counter: list[int]      = [0]
    where_fragment = root.to_sql(params, counter)

    return where_fragment, params


def get_field_reference(allowed_fields: dict) -> list[dict]:
    """
    Returns all fields with their keys, labels, units, categories, and known aliases.
    Used by the ``GET /api/v1/screener/query/fields`` endpoint.
    """
    # Build reverse map: field_key → list of human-readable aliases
    reverse: dict[str, list[str]] = {}
    for alias, key in EXTRA_ALIASES.items():
        if key in allowed_fields:
            reverse.setdefault(key, []).append(alias)

    result = []
    for key, info in allowed_fields.items():
        result.append({
            "key":      key,
            "label":    info["label"],
            "unit":     info["unit"],
            "category": info["cat"],
            "type":     info["type"],
            "aliases":  sorted(reverse.get(key, [])),
        })

    return result
