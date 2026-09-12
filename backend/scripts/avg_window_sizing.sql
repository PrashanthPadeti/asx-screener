-- Rolling averages: two defects, measured apart
-- ==============================================
-- yearly_compute._avg(values, n) takes values[-n:] — the last n LIST ENTRIES
-- — then drops every None among them and averages what is left:
--
--     vals = [_f(v) for v in values[-n:]]
--     vals = [v for v in vals if v is not None]
--     return sum(vals) / len(vals) if vals else None
--
-- Two independent failures live in those three lines, and they deserve
-- separate policies because they are separate facts.
--
--   WINDOW INTEGRITY    the last n rows may span more than n fiscal years.
--                       A company reporting 2018, 2020, 2021, 2022 has its
--                       "3-year average" taken over 2020-2022 — correct — but
--                       one reporting 2016, 2019, 2022 has it taken over seven
--                       years while the column still says three.
--
--   COVERAGE INTEGRITY  among those rows, None values are silently dropped.
--                       avg_roe_3y can be one year's ROE labelled as three,
--                       with nothing distinguishing it from a genuine one.
--
-- A company can fail either without the other: a contiguous three-year window
-- containing one usable ROE is not the same defect as a five-year-labelled
-- average spanning eight fiscal years. Counting them together would produce
-- one number that answers neither question.
--
--     sudo -u postgres psql -d asx_screener -f scripts/avg_window_sizing.sql
--
-- Read-only. It measures; the policy is a methodology decision. Requiring all
-- n observations, or declaring an explicit minimum coverage, or accepting the
-- current behaviour under a documented rule are all defensible — but not
-- "take whatever non-null values happen to be in the last n rows and still
-- call it an n-year average".

\pset format aligned
\pset null '—'

CREATE TEMP VIEW avg_window AS
WITH ranked AS (
    SELECT ym.asx_code, ym.fiscal_year,
           ym.roe, ym.roa, ym.roce, ym.roic,
           row_number() OVER (PARTITION BY ym.asx_code
                               ORDER BY ym.fiscal_year DESC) AS recency,
           max(ym.fiscal_year) OVER (PARTITION BY ym.asx_code) AS latest_fy
      FROM market.yearly_metrics ym
      JOIN screener.universe u
        ON u.asx_code = ym.asx_code AND u.status = 'active'
)
SELECT asx_code,
       max(latest_fy)                                   AS fy,
       -- Window: how far back the last n ROWS actually reach.
       max(latest_fy) - min(fiscal_year) FILTER (WHERE recency <= 3) AS span_3,
       max(latest_fy) - min(fiscal_year) FILTER (WHERE recency <= 5) AS span_5,
       count(*)      FILTER (WHERE recency <= 3)        AS rows_3,
       count(*)      FILTER (WHERE recency <= 5)        AS rows_5,
       -- Coverage: usable observations inside those rows.
       count(roe)    FILTER (WHERE recency <= 3)        AS roe_3,
       count(roe)    FILTER (WHERE recency <= 5)        AS roe_5,
       count(roa)    FILTER (WHERE recency <= 3)        AS roa_3,
       count(roce)   FILTER (WHERE recency <= 3)        AS roce_3,
       count(roic)   FILTER (WHERE recency <= 3)        AS roic_3
  FROM ranked
 GROUP BY asx_code;

-- ── Window integrity, on its own ────────────────────────────────────────────
-- Only companies with enough rows to form the window at all. Fewer rows than n
-- is a third thing — too little history — and _avg already returns a shorter
-- average for those rather than None, which is the coverage defect, not this
-- one.

SELECT '3-year' AS window,
       count(*) FILTER (WHERE rows_3 = 3)                      AS have_window,
       count(*) FILTER (WHERE rows_3 = 3 AND span_3 = 2)        AS contiguous,
       count(*) FILTER (WHERE rows_3 = 3 AND span_3 > 2)        AS overspanning,
       max(span_3) FILTER (WHERE rows_3 = 3)                    AS worst_span,
       count(*) FILTER (WHERE rows_3 < 3)                       AS too_few_rows
  FROM avg_window
UNION ALL
SELECT '5-year',
       count(*) FILTER (WHERE rows_5 = 5),
       count(*) FILTER (WHERE rows_5 = 5 AND span_5 = 4),
       count(*) FILTER (WHERE rows_5 = 5 AND span_5 > 4),
       max(span_5) FILTER (WHERE rows_5 = 5),
       count(*) FILTER (WHERE rows_5 < 5)
  FROM avg_window;

-- ── Coverage integrity, on its own ──────────────────────────────────────────
-- Among companies whose 3-row window IS contiguous, so the window defect
-- cannot be confused with this one: how many usable observations does the
-- average actually rest on?

SELECT 'roe'  AS metric, roe_3  AS observations, count(*) AS companies
  FROM avg_window WHERE rows_3 = 3 AND span_3 = 2 GROUP BY 2
UNION ALL
SELECT 'roa',  roa_3,  count(*) FROM avg_window
 WHERE rows_3 = 3 AND span_3 = 2 GROUP BY 2
UNION ALL
SELECT 'roce', roce_3, count(*) FROM avg_window
 WHERE rows_3 = 3 AND span_3 = 2 GROUP BY 2
UNION ALL
SELECT 'roic', roic_3, count(*) FROM avg_window
 WHERE rows_3 = 3 AND span_3 = 2 GROUP BY 2
 ORDER BY 1, 2 DESC;

-- ── The two together ────────────────────────────────────────────────────────
-- What each candidate policy would cost for avg_roe_3y specifically, since
-- that is the one feeding a governed rolling average.

SELECT 'any usable observation (today)'          AS policy,
       count(*) FILTER (WHERE roe_3 >= 1)        AS scored,
       count(*) FILTER (WHERE roe_3 = 0)         AS withheld
  FROM avg_window
UNION ALL
SELECT 'contiguous window, any observation',
       count(*) FILTER (WHERE rows_3 = 3 AND span_3 = 2 AND roe_3 >= 1),
       count(*) - count(*) FILTER (WHERE rows_3 = 3 AND span_3 = 2 AND roe_3 >= 1)
  FROM avg_window
UNION ALL
SELECT 'contiguous window, 2 of 3 observations',
       count(*) FILTER (WHERE rows_3 = 3 AND span_3 = 2 AND roe_3 >= 2),
       count(*) - count(*) FILTER (WHERE rows_3 = 3 AND span_3 = 2 AND roe_3 >= 2)
  FROM avg_window
UNION ALL
SELECT 'contiguous window, all 3 observations',
       count(*) FILTER (WHERE rows_3 = 3 AND span_3 = 2 AND roe_3 = 3),
       count(*) - count(*) FILTER (WHERE rows_3 = 3 AND span_3 = 2 AND roe_3 = 3)
  FROM avg_window;
