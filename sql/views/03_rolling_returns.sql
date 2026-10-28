-- Rolling 1-, 3- and 5-year CAGR, sampled at each month-end.
-- CAGR = (end/start)^(365/calendar days) - 1. A window counts only if the scheme
-- has a NAV at its start (no 5-year CAGR from 3 years of data), real NAVs on at
-- least min_coverage of the window's trading days, and start/end NAVs at most 7 days stale.
DROP MATERIALIZED VIEW IF EXISTS rolling_returns CASCADE;
CREATE MATERIALIZED VIEW rolling_returns AS
WITH month_ends AS (
    SELECT MAX(cal_date) AS end_date
    FROM trading_calendar
    GROUP BY date_trunc('month', cal_date)
), windows AS (
    SELECT m.end_date, y.window_years,
           (SELECT MAX(c.cal_date) FROM trading_calendar c
            WHERE c.cal_date <= (m.end_date - make_interval(years => y.window_years))::date) AS start_date
    FROM month_ends m
    CROSS JOIN (VALUES (1), (3), (5)) AS y (window_years)
), sized AS (
    SELECT w.*,
           (SELECT COUNT(*) FROM trading_calendar c
            WHERE c.cal_date > w.start_date AND c.cal_date <= w.end_date) AS expected_days
    FROM windows w
    WHERE w.start_date IS NOT NULL
)
SELECT e.scheme_code,
       w.window_years,
       w.start_date,
       w.end_date,
       s.nav AS start_nav,
       e.nav AS end_nav,
       POWER(e.nav / s.nav, 365.0 / (w.end_date - w.start_date)) - 1 AS cagr,
       (e.obs_count - s.obs_count)::float8 / w.expected_days AS coverage
FROM sized w
JOIN nav_filled s ON s.nav_date = w.start_date
JOIN nav_filled e ON e.nav_date = w.end_date AND e.scheme_code = s.scheme_code
WHERE (e.obs_count - s.obs_count)::float8 / w.expected_days
      >= (SELECT value FROM params WHERE key = 'min_coverage')
  AND w.start_date - s.source_date <= 7
  AND w.end_date - e.source_date <= 7;
CREATE UNIQUE INDEX ON rolling_returns (scheme_code, window_years, end_date);
