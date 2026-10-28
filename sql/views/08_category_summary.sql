-- Category scorecard per plan type and window length, over funds with at least
-- min_windows rolling windows. 'All' pools the three categories.
--   pooled_beat_rate:             share of all fund-windows that beat the index fund
--   share_funds_beating:          share of funds whose median excess return is positive
--   share_median_excess_negative: share of funds whose median excess return is negative
DROP MATERIALIZED VIEW IF EXISTS category_summary CASCADE;
CREATE MATERIALIZED VIEW category_summary AS
SELECT COALESCE(f.category, 'All') AS category,
       f.plan_type,
       f.window_years,
       COUNT(*) AS n_funds,
       SUM(f.n_windows) AS n_fund_windows,
       SUM(f.beat_rate * f.n_windows) / SUM(f.n_windows) AS pooled_beat_rate,
       AVG((f.median_excess > 0)::int) AS share_funds_beating,
       AVG((f.median_excess < 0)::int) AS share_median_excess_negative,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY f.median_excess) AS median_fund_excess,
       MIN(f.first_window_end) AS first_window_end,
       MAX(f.last_window_end) AS last_window_end
FROM fund_beat_rates f
WHERE f.n_windows >= (SELECT value FROM params WHERE key = 'min_windows')
GROUP BY GROUPING SETS ((f.category, f.plan_type, f.window_years), (f.plan_type, f.window_years));
