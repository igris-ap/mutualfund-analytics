-- Survivorship check over the last analysis_years: how many in-scope schemes existed
-- at the start of the window, how many still publish a NAV now, and how many closed
-- or merged in between. 'Alive now' means a NAV within 7 days of the latest trading day.
DROP MATERIALIZED VIEW IF EXISTS survivorship CASCADE;
CREATE MATERIALIZED VIEW survivorship AS
WITH b AS (
    SELECT l.end_date,
           (l.end_date - make_interval(years => (SELECT value FROM params WHERE key = 'analysis_years')::int))::date AS start_date
    FROM (SELECT MAX(cal_date) AS end_date FROM trading_calendar) l
), s AS (
    SELECT sc.category, sc.plan_type,
           sc.first_nav_date <= b.start_date AND sc.last_nav_date >= b.start_date AS at_start,
           sc.last_nav_date >= b.end_date - 7 AS at_end,
           sc.first_nav_date > b.start_date AS launched_since,
           b.start_date, b.end_date
    FROM schemes sc
    CROSS JOIN b
    WHERE NOT sc.is_benchmark
)
SELECT COALESCE(category, 'All') AS category,
       plan_type,
       MIN(start_date) AS window_start,
       MIN(end_date) AS window_end,
       COUNT(*) FILTER (WHERE at_start) AS schemes_at_start,
       COUNT(*) FILTER (WHERE at_end) AS schemes_at_end,
       COUNT(*) FILTER (WHERE at_start AND NOT at_end) AS closed_or_merged,
       COUNT(*) FILTER (WHERE launched_since) AS launched_since,
       COUNT(*) FILTER (WHERE launched_since AND NOT at_end) AS launched_and_closed
FROM s
GROUP BY GROUPING SETS ((category, plan_type), (plan_type));
