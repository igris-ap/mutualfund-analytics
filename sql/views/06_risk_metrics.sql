-- Risk metrics over the trailing risk_window_years, ending on the latest trading day.
--   volatility   = stdev(daily return) * sqrt(252)
--   sharpe       = (mean daily return * 252 - rf) / volatility
--   sortino      = (mean daily return * 252 - rf) / (downside deviation * sqrt(252)),
--                  downside deviation measured against the daily risk-free rate
--   max_drawdown = worst fall from a running peak (negative number)
-- Only schemes with a fresh NAV at the window start and end, and min_coverage real
-- NAVs in between, are scored.
DROP MATERIALIZED VIEW IF EXISTS risk_metrics CASCADE;
CREATE MATERIALIZED VIEW risk_metrics AS
WITH p AS (
    SELECT MAX(value) FILTER (WHERE key = 'risk_free_rate') AS rf,
           MAX(value) FILTER (WHERE key = 'risk_window_years')::int AS years,
           MAX(value) FILTER (WHERE key = 'min_coverage') AS min_coverage
    FROM params
), bounds AS (
    SELECT l.end_date,
           (SELECT MAX(c.cal_date) FROM trading_calendar c
            WHERE c.cal_date <= (l.end_date - make_interval(years => p.years))::date) AS start_date
    FROM (SELECT MAX(cal_date) AS end_date FROM trading_calendar) l
    CROSS JOIN p
), spans AS (
    SELECT s.scheme_code, b.start_date, b.end_date, s.nav AS start_nav, e.nav AS end_nav,
           (e.obs_count - s.obs_count)::float8
             / (SELECT COUNT(*) FROM trading_calendar c
                WHERE c.cal_date > b.start_date AND c.cal_date <= b.end_date) AS coverage
    FROM bounds b
    JOIN nav_filled s ON s.nav_date = b.start_date
    JOIN nav_filled e ON e.nav_date = b.end_date AND e.scheme_code = s.scheme_code
    WHERE b.start_date - s.source_date <= 7 AND b.end_date - e.source_date <= 7
), daily AS (
    SELECT n.scheme_code,
           n.nav / LAG(n.nav) OVER w - 1 AS ret,
           n.nav / MAX(n.nav) OVER w - 1 AS drawdown
    FROM nav_filled n
    JOIN spans sp ON sp.scheme_code = n.scheme_code
    WHERE n.nav_date BETWEEN sp.start_date AND sp.end_date
    WINDOW w AS (PARTITION BY n.scheme_code ORDER BY n.nav_date)
), stats AS (
    SELECT d.scheme_code,
           AVG(d.ret) AS mean_daily,
           STDDEV_SAMP(d.ret) AS sd_daily,
           SQRT(AVG(POWER(LEAST(d.ret - p.rf / 252, 0), 2)) FILTER (WHERE d.ret IS NOT NULL)) AS downside_daily,
           MIN(d.drawdown) AS max_drawdown
    FROM daily d
    CROSS JOIN p
    GROUP BY d.scheme_code
)
SELECT sp.scheme_code,
       sp.start_date,
       sp.end_date,
       sp.coverage,
       POWER(sp.end_nav / sp.start_nav, 365.0 / (sp.end_date - sp.start_date)) - 1 AS cagr,
       st.sd_daily * SQRT(252) AS volatility,
       (st.mean_daily * 252 - p.rf) / NULLIF(st.sd_daily * SQRT(252), 0) AS sharpe,
       (st.mean_daily * 252 - p.rf) / NULLIF(st.downside_daily * SQRT(252), 0) AS sortino,
       st.max_drawdown
FROM spans sp
JOIN stats st ON st.scheme_code = sp.scheme_code
CROSS JOIN p
WHERE sp.coverage >= p.min_coverage;
CREATE UNIQUE INDEX ON risk_metrics (scheme_code);
