-- Common trading calendar: weekdays on which at least half of the schemes alive that
-- day published a NAV. Drops stray holiday NAVs but keeps every market day.
DROP MATERIALIZED VIEW IF EXISTS trading_calendar CASCADE;
CREATE MATERIALIZED VIEW trading_calendar AS
WITH spans AS (
    SELECT scheme_code, MIN(nav_date) AS first_date, MAX(nav_date) AS last_date
    FROM nav_daily
    GROUP BY scheme_code
), reported AS (
    SELECT nav_date, COUNT(*) AS n_reported
    FROM nav_daily
    WHERE EXTRACT(ISODOW FROM nav_date) < 6
    GROUP BY nav_date
)
SELECT r.nav_date AS cal_date
FROM reported r
WHERE r.n_reported >= 0.5 * (SELECT COUNT(*) FROM spans s
                             WHERE r.nav_date BETWEEN s.first_date AND s.last_date)
ORDER BY 1;
CREATE UNIQUE INDEX ON trading_calendar (cal_date);
