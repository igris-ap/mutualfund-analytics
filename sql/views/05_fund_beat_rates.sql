-- Per fund and window length: share of rolling windows in which it beat its index
-- fund (beat rate), and its median / mean excess return.
DROP MATERIALIZED VIEW IF EXISTS fund_beat_rates CASCADE;
CREATE MATERIALIZED VIEW fund_beat_rates AS
SELECT scheme_code,
       category,
       plan_type,
       window_years,
       COUNT(*) AS n_windows,
       AVG(beat::int) AS beat_rate,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY excess_return) AS median_excess,
       AVG(excess_return) AS mean_excess,
       MIN(end_date) AS first_window_end,
       MAX(end_date) AS last_window_end
FROM excess_returns
GROUP BY scheme_code, category, plan_type, window_years;
CREATE UNIQUE INDEX ON fund_beat_rates (scheme_code, window_years);
