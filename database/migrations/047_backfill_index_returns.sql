-- Migration 047: Backfill period returns for market.index_prices
-- Problem: The index_prices table has 12,000+ rows of close_price data but
-- return_1w / return_1m / return_3m / return_1y are NULL because the
-- Python engine was stripping the lookback-context window before computing.
-- Solution: Use LAG() window function to compute returns directly in SQL.
--
-- Trading-day lookbacks (matching compute engine logic):
--   1W  =  5 trading days
--   1M  = 21 trading days
--   3M  = 63 trading days
--   6M  = 126 trading days
--   1Y  = 252 trading days

WITH ranked AS (
    SELECT
        index_code,
        price_date,
        close_price,
        ROW_NUMBER() OVER (PARTITION BY index_code ORDER BY price_date) AS rn
    FROM market.index_prices
    WHERE close_price IS NOT NULL
),
returns AS (
    SELECT
        r.index_code,
        r.price_date,
        -- 1D: prior trading day
        CASE WHEN p1.close_price > 0
             THEN (r.close_price - p1.close_price) / p1.close_price END AS return_1d,
        -- 1W: 5 trading days ago
        CASE WHEN p5.close_price > 0
             THEN (r.close_price - p5.close_price) / p5.close_price END AS return_1w,
        -- 1M: 21 trading days ago
        CASE WHEN p21.close_price > 0
             THEN (r.close_price - p21.close_price) / p21.close_price END AS return_1m,
        -- 3M: 63 trading days ago
        CASE WHEN p63.close_price > 0
             THEN (r.close_price - p63.close_price) / p63.close_price END AS return_3m,
        -- 6M: 126 trading days ago
        CASE WHEN p126.close_price > 0
             THEN (r.close_price - p126.close_price) / p126.close_price END AS return_6m,
        -- 1Y: 252 trading days ago
        CASE WHEN p252.close_price > 0
             THEN (r.close_price - p252.close_price) / p252.close_price END AS return_1y
    FROM ranked r
    -- Self-joins for each lookback window
    LEFT JOIN ranked p1   ON p1.index_code  = r.index_code AND p1.rn  = r.rn - 1
    LEFT JOIN ranked p5   ON p5.index_code  = r.index_code AND p5.rn  = r.rn - 5
    LEFT JOIN ranked p21  ON p21.index_code = r.index_code AND p21.rn = r.rn - 21
    LEFT JOIN ranked p63  ON p63.index_code = r.index_code AND p63.rn = r.rn - 63
    LEFT JOIN ranked p126 ON p126.index_code = r.index_code AND p126.rn = r.rn - 126
    LEFT JOIN ranked p252 ON p252.index_code = r.index_code AND p252.rn = r.rn - 252
),
ytd_base AS (
    -- Last trading day of prior year, per index
    SELECT DISTINCT ON (index_code, EXTRACT(year FROM price_date))
        index_code,
        EXTRACT(year FROM price_date)::int + 1 AS target_year,
        close_price AS year_start_close
    FROM market.index_prices
    WHERE close_price IS NOT NULL
    ORDER BY index_code, EXTRACT(year FROM price_date), price_date DESC
),
ytd_returns AS (
    SELECT
        ip.index_code,
        ip.price_date,
        CASE WHEN yb.year_start_close > 0
             THEN (ip.close_price - yb.year_start_close) / yb.year_start_close END AS return_ytd
    FROM market.index_prices ip
    JOIN ytd_base yb
      ON yb.index_code  = ip.index_code
     AND yb.target_year = EXTRACT(year FROM ip.price_date)::int
    WHERE ip.close_price IS NOT NULL
)
UPDATE market.index_prices ip
SET
    return_1d  = r.return_1d,
    return_1w  = r.return_1w,
    return_1m  = r.return_1m,
    return_3m  = r.return_3m,
    return_6m  = r.return_6m,
    return_1y  = r.return_1y,
    return_ytd = y.return_ytd
FROM returns r
LEFT JOIN ytd_returns y
  ON y.index_code  = r.index_code
 AND y.price_date  = r.price_date
WHERE ip.index_code  = r.index_code
  AND ip.price_date  = r.price_date;

-- Verify: show latest row per index with return columns populated
SELECT
    index_code,
    price_date,
    close_price,
    ROUND(return_1d  * 100, 2) AS "1D%",
    ROUND(return_1w  * 100, 2) AS "1W%",
    ROUND(return_1m  * 100, 2) AS "1M%",
    ROUND(return_3m  * 100, 2) AS "3M%",
    ROUND(return_1y  * 100, 2) AS "1Y%",
    ROUND(return_ytd * 100, 2) AS "YTD%"
FROM market.index_prices
WHERE (index_code, price_date) IN (
    SELECT index_code, MAX(price_date)
    FROM market.index_prices
    GROUP BY index_code
)
ORDER BY index_code;
