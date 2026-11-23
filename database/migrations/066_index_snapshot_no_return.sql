-- Migration 066: market.index_snapshots gains a column for "we do not know"
--
-- The index snapshot stage has refused to publish since 20 November 2026:
--
--   SnapshotIncomplete: ASX300: 1 of 277 constituents have no return_1w, and
--   index_snapshots has no column to record that. Add one rather than counting
--   them as unchanged.
--
-- That refusal was correct and deliberate. The table could record gainers,
-- losers and unchanged, and nothing else, so a constituent whose 1-week return
-- is unknown had no truthful destination: the only bucket wide enough to hold
-- it was `unchanged`, which asserts the price did not move. The engine would
-- rather stop than make that claim.
--
-- This is the column the refusal asked for. It is deliberately NULLable and
-- carries no DEFAULT: rows written before today genuinely do not know how many
-- constituents were unattributed, and a DEFAULT 0 would back-fill a confident
-- "none were missing" across every historical snapshot -- re-creating, in the
-- store, exactly the destruction the producer refused to perform.
--
--   no_return IS NULL   the snapshot predates this column; coverage unknown
--   no_return = 0       measured, and every constituent had a return
--   no_return > 0       measured, and this many did not
--
-- With the column present, `stock_count` is partitioned exactly:
--     gainers + losers + unchanged + no_return = stock_count
-- which the producer now asserts rather than assumes.

ALTER TABLE market.index_snapshots
    ADD COLUMN IF NOT EXISTS no_return INT;

COMMENT ON COLUMN market.index_snapshots.no_return IS
    'Constituents with no return_1w at snapshot time. NULL means the snapshot '
    'predates the column and its coverage is unknown -- it does not mean zero.';
