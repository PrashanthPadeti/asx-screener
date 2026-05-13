-- Migration 048: Backfill period returns for market.fund_prices
-- Same root cause as migration 047 (index_prices): the Python engine was
-- stripping the 400-day lookback context before computing rolling returns,
-- leaving return_1w / return_1m / return_1y / return_ytd as NULL.
--
-- Trading-day lookbacks:
--   1W  =  5 trading days
--   1M  = 21 trading days
--   3M  = 63 trading days
--   6M  = 126 trading days
--   1Y  = 252 trading days

WITH ranked AS (
    SELECT
        asx_code,
        price_date,
        close_price,
        ROW_NUMBER() OVER (PARTITION BY asx_code ORDER BY price_date) AS rn
    FROM market.fund_prices
    WHERE close_price IS NOT NULL
),
returns AS (
    SELECT
        r.asx_code,
        r.price_date,
        CASE WHEN p1.close_price   > 0 THEN (r.close_price - p1.close_price)   / p1.close_price   END AS return_1d,
        CASE WHEN p5.close_price   > 0 THEN (r.close_price - p5.close_price)   / p5.close_price   END AS return_1w,
        CASE WHEN p21.close_price  > 0 THEN (r.close_price - p21.close_price)  / p21.close_price  END AS return_1m,
        CASE WHEN p63.close_price  > 0 THEN (r.close_price - p63.close_price)  / p63.close_price  END AS return_3m,
        CASE WHEN p126.close_price > 0 THEN (r.close_price - p126.close_price) / p126.close_price END AS return_6m,
        CASE WHEN p252.close_price > 0 THEN (r.close_price - p252.close_price) / p252.close_price END AS return_1y
    FROM ranked r
    LEFT JOIN ranked p1   ON p1.asx_code   = r.asx_code AND p1.rn   = r.rn - 1
    LEFT JOIN ranked p5   ON p5.asx_code   = r.asx_code AND p5.rn   = r.rn - 5
    LEFT JOIN ranked p21  ON p21.asx_code  = r.asx_code AND p21.rn  = r.rn - 21
    LEFT JOIN ranked p63  ON p63.asx_code  = r.asx_code AND p63.rn  = r.rn - 63
    LEFT JOIN ranked p126 ON p126.asx_code = r.asx_code AND p126.rn = r.rn - 126
    LEFT JOIN ranked p252 ON p252.asx_code = r.asx_code AND p252.rn = r.rn - 252
),
ytd_base AS (
    SELECT DISTINCT ON (asx_code, EXTRACT(year FROM price_date))
        asx_code,
        EXTRACT(year FROM price_date)::int + 1 AS target_year,
        close_price AS year_start_close
    FROM market.fund_prices
    WHERE close_price IS NOT NULL
    ORDER BY asx_code, EXTRACT(year FROM price_date), price_date DESC
),
ytd_returns AS (
    SELECT
        fp.asx_code,
        fp.price_date,
        CASE WHEN yb.year_start_close > 0
             THEN (fp.close_price - yb.year_start_close) / yb.year_start_close END AS return_ytd
    FROM market.fund_prices fp
    JOIN ytd_base yb
      ON yb.asx_code    = fp.asx_code
     AND yb.target_year = EXTRACT(year FROM fp.price_date)::int
    WHERE fp.close_price IS NOT NULL
)
UPDATE market.fund_prices fp
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
  ON y.asx_code   = r.asx_code
 AND y.price_date = r.price_date
WHERE fp.asx_code   = r.asx_code
  AND fp.price_date = r.price_date;

-- Verify: latest row per fund with return columns
SELECT
    asx_code,
    price_date,
    close_price,
    ROUND(return_1w  * 100, 2) AS "1W%",
    ROUND(return_1m  * 100, 2) AS "1M%",
    ROUND(return_1y  * 100, 2) AS "1Y%",
    ROUND(return_ytd * 100, 2) AS "YTD%"
FROM market.fund_prices
WHERE (asx_code, price_date) IN (
    SELECT asx_code, MAX(price_date)
    FROM market.fund_prices
    GROUP BY asx_code
)
ORDER BY asx_code
LIMIT 20;
