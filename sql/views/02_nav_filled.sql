-- Each scheme's NAV on every calendar day between its first and last NAV, forward-filled
-- across gaps. Used only for return calculations, so a missing day never turns into a
-- fake multi-day return.
--   source_date: the date of the real NAV a filled value comes from. Windows reject a
--                start or end NAV more than 7 days stale (e.g. inside a data gap).
--   obs_count:   running count of real NAVs, so a window's coverage is
--                obs_count(end) - obs_count(start).
DROP MATERIALIZED VIEW IF EXISTS nav_filled CASCADE;
CREATE MATERIALIZED VIEW nav_filled AS
WITH spans AS (
    SELECT scheme_code, MIN(nav_date) AS first_date, MAX(nav_date) AS last_date
    FROM nav_daily
    GROUP BY scheme_code
), grid AS (
    SELECT s.scheme_code, c.cal_date, n.nav
    FROM spans s
    JOIN trading_calendar c ON c.cal_date BETWEEN s.first_date AND s.last_date
    LEFT JOIN nav_daily n ON n.scheme_code = s.scheme_code AND n.nav_date = c.cal_date
), grouped AS (
    SELECT scheme_code, cal_date, nav,
           COUNT(nav) OVER (PARTITION BY scheme_code ORDER BY cal_date) AS obs_count
    FROM grid
)
SELECT scheme_code,
       cal_date AS nav_date,
       (FIRST_VALUE(nav) OVER fill)::float8 AS nav,
       FIRST_VALUE(cal_date) OVER fill AS source_date,
       nav IS NOT NULL AS observed,
       obs_count
FROM grouped
WHERE obs_count > 0
WINDOW fill AS (PARTITION BY scheme_code, obs_count ORDER BY cal_date);
CREATE UNIQUE INDEX ON nav_filled (scheme_code, nav_date);
CREATE INDEX ON nav_filled (nav_date);
