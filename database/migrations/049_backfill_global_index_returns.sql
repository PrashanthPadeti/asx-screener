-- Migration 049: Backfill period returns for market.global_index_prices
-- Same root cause as 047/048: lookback context was stripped before compute.

WITH ranked AS (
    SELECT
        index_code,
        price_date,
        close_price,
        ROW_NUMBER() OVER (PARTITION BY index_code ORDER BY price_date) AS rn
    FROM market.global_index_prices
    WHERE close_price IS NOT NULL
),
returns AS (
    SELECT
        r.index_code,
        r.price_date,
        CASE WHEN p1.close_price   > 0 THEN (r.close_price - p1.close_price)   / p1.close_price   END AS return_1d,
        CASE WHEN p5.close_price   > 0 THEN (r.close_price - p5.close_price)   / p5.close_price   END AS return_1w,
        CASE WHEN p21.close_price  > 0 THEN (r.close_price - p21.close_price)  / p21.close_price  END AS return_1m,
        CASE WHEN p63.close_price  > 0 THEN (r.close_price - p63.close_price)  / p63.close_price  END AS return_3m,
        CASE WHEN p126.close_price > 0 THEN (r.close_price - p126.close_price) / p126.close_price END AS return_6m,
        CASE WHEN p252.close_price > 0 THEN (r.close_price - p252.close_price) / p252.close_price END AS return_1y
    FROM ranked r
    LEFT JOIN ranked p1   ON p1.index_code   = r.index_code AND p1.rn   = r.rn - 1
    LEFT JOIN ranked p5   ON p5.index_code   = r.index_code AND p5.rn   = r.rn - 5
    LEFT JOIN ranked p21  ON p21.index_code  = r.index_code AND p21.rn  = r.rn - 21
    LEFT JOIN ranked p63  ON p63.index_code  = r.index_code AND p63.rn  = r.rn - 63
    LEFT JOIN ranked p126 ON p126.index_code = r.index_code AND p126.rn = r.rn - 126
    LEFT JOIN ranked p252 ON p252.index_code = r.index_code AND p252.rn = r.rn - 252
),
ytd_base AS (
    SELECT DISTINCT ON (index_code, EXTRACT(year FROM price_date))
        index_code,
        EXTRACT(year FROM price_date)::int + 1 AS target_year,
        close_price AS year_start_close
    FROM market.global_index_prices
    WHERE close_price IS NOT NULL
    ORDER BY index_code, EXTRACT(year FROM price_date), price_date DESC
),
ytd_returns AS (
    SELECT
        gp.index_code,
        gp.price_date,
        CASE WHEN yb.year_start_close > 0
             THEN (gp.close_price - yb.year_start_close) / yb.year_start_close END AS return_ytd
    FROM market.global_index_prices gp
    JOIN ytd_base yb
      ON yb.index_code  = gp.index_code
     AND yb.target_year = EXTRACT(year FROM gp.price_date)::int
    WHERE gp.close_price IS NOT NULL
)
UPDATE market.global_index_prices gp
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
WHERE gp.index_code  = r.index_code
  AND gp.price_date  = r.price_date;

-- Verify
SELECT
    index_code,
    price_date,
    close_price,
    ROUND(return_1w  * 100, 2) AS "1W%",
    ROUND(return_1m  * 100, 2) AS "1M%",
    ROUND(return_3m  * 100, 2) AS "3M%",
    ROUND(return_1y  * 100, 2) AS "1Y%",
    ROUND(return_ytd * 100, 2) AS "YTD%"
FROM market.global_index_prices
WHERE (index_code, price_date) IN (
    SELECT index_code, MAX(price_date)
    FROM market.global_index_prices
    GROUP BY index_code
)
ORDER BY index_code;
