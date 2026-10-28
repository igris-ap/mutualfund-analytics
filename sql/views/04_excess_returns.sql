-- Each active fund's rolling CAGR minus its category's index fund over the same window.
-- Both plans are kept: direct-vs-index isolates active management, regular-vs-index
-- adds the distributor commission on top.
DROP MATERIALIZED VIEW IF EXISTS excess_returns CASCADE;
CREATE MATERIALIZED VIEW excess_returns AS
SELECT r.scheme_code,
       sc.category,
       sc.plan_type,
       r.window_years,
       r.start_date,
       r.end_date,
       r.cagr AS fund_cagr,
       b.cagr AS bench_cagr,
       r.cagr - b.cagr AS excess_return,
       r.cagr > b.cagr AS beat
FROM rolling_returns r
JOIN schemes sc ON sc.scheme_code = r.scheme_code AND NOT sc.is_benchmark
JOIN benchmarks bm ON bm.category = sc.category
JOIN rolling_returns b ON b.scheme_code = bm.scheme_code
                      AND b.window_years = r.window_years
                      AND b.end_date = r.end_date;
CREATE INDEX ON excess_returns (scheme_code, window_years);
