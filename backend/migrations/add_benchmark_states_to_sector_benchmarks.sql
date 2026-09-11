-- Peer benchmarks lose their semantics at the persistence boundary too.
--
-- market.sector_benchmarks has fixed numeric columns — pe_ratio_median,
-- roe_p25, debt_to_equity_median and so on — so a withheld benchmark can only
-- be written as NULL. That is the same defect already fixed for company
-- metrics, arriving one table over: NULL cannot say whether the metric is out
-- of domain for every peer in the sector, whether the dividend feed broke,
-- whether the sector is structurally too small, or whether coverage was too
-- thin. Those have four different remediations and one representation.
--
-- It also carries a single `stock_count` for the whole sector, shared by
-- every metric. A Financials row saying n=142 tells a reader nothing about
-- how many of those 142 could carry a debt-to-equity observation (none) or a
-- grossed-up yield (all of them). One denominator forced to mean many things.
--
-- Same sparse sidecar as screener.universe.metric_states, for the same
-- reasons: the numeric columns stay exactly as they are so every existing
-- reader keeps working, and an entry appears only where there is something to
-- say beyond the number.
--
--   {"debt_to_equity": {"state":"not_meaningful",
--                       "reason_code":"out_of_domain_for_all",
--                       "n_total_peers":142,"n_applicable_peers":0,
--                       "n_valid_peers":0},
--    "grossed_up_yield": {"state":"applicable",
--                         "n_total_peers":142,"n_applicable_peers":142,
--                         "n_valid_peers":118,"coverage_pct":83.1}}
--
-- Note the second entry: an APPLICABLE benchmark still gets a payload here,
-- unlike the company sidecar. The counts are not an exception report — they
-- are what lets a surface say "4.8%, 118 of 142 valid observations" instead
-- of a bare percentage whose denominator nobody can see.

-- Nullable, no default, for the reason set out in
-- add_metric_states_to_universe.sql: NULL means never assessed, '{}' means
-- assessed with nothing to record. The distinction is stronger here than on
-- the company sidecar, because this payload is not an exception report — an
-- APPLICABLE benchmark still writes its population counts. So '{}' on a
-- benchmark row would claim it was computed and had nothing to say, which is
-- never true of a valid benchmark.

ALTER TABLE market.sector_benchmarks
    ADD COLUMN IF NOT EXISTS benchmark_states JSONB;

COMMENT ON COLUMN market.sector_benchmarks.benchmark_states IS
    'Per-metric benchmark state: metric -> {state, reason_code, n_total_peers, '
    'n_applicable_peers, n_valid_peers, coverage_pct}. A numeric median column '
    'that is NULL with no entry here predates this contract; a NULL with an '
    'entry has a stated reason. Applicable benchmarks carry counts too, so the '
    'denominator is always visible.';


-- Same-run consistency. A company factor score computed under one run must
-- not be displayed against a sector benchmark built from a different
-- applicability and source-health state — the customer would be comparing a
-- valid individual metric with a peer statistic assembled under different
-- rules, and nothing on the page would say so.

ALTER TABLE market.sector_benchmarks
    ADD COLUMN IF NOT EXISTS compute_run_id BIGINT
        REFERENCES screener.compute_runs (id);

COMMENT ON COLUMN market.sector_benchmarks.compute_run_id IS
    'The run that produced this benchmark. Must match the compute_run_id of '
    'the screener.universe rows it contextualises: a factor score and the '
    'peer statistic shown beside it have to come from the same assessment set '
    'and the same model version.';

CREATE INDEX IF NOT EXISTS idx_sector_benchmarks_compute_run
    ON market.sector_benchmarks (compute_run_id);
