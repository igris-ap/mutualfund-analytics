-- Direct vs regular plan of the same fund (same base_scheme_key), for pairs still
-- running today.
--   annual_gap: direct CAGR minus regular CAGR over their common history, capped at
--               the last analysis_years years.
--   SIP: sip_amount invested on the first trading day of each of the last
--        analysis_years * 12 months, valued on the latest trading day. Only pairs with
--        the full history get SIP numbers.
DROP MATERIALIZED VIEW IF EXISTS direct_regular_gap CASCADE;
CREATE MATERIALIZED VIEW direct_regular_gap AS
WITH p AS (
    SELECT MAX(value) FILTER (WHERE key = 'sip_amount') AS sip_amount,
           MAX(value) FILTER (WHERE key = 'analysis_years')::int AS years
    FROM params
), last_day AS (
    SELECT MAX(cal_date) AS end_date FROM trading_calendar
), pairs AS (
    SELECT d.base_scheme_key, d.category,
           d.scheme_code AS direct_code, d.scheme_name AS direct_name,
           r.scheme_code AS regular_code, r.scheme_name AS regular_name,
           GREATEST(d.first_nav_date, r.first_nav_date) AS common_first_date
    FROM schemes d
    JOIN schemes r ON r.base_scheme_key = d.base_scheme_key AND r.plan_type = 'regular'
    WHERE d.plan_type = 'direct' AND NOT d.is_benchmark
), sip_months AS (
    SELECT MIN(c.cal_date) AS sip_date
    FROM trading_calendar c
    CROSS JOIN last_day l
    CROSS JOIN p
    WHERE c.cal_date >= date_trunc('month', l.end_date) - make_interval(months => p.years * 12 - 1)
    GROUP BY date_trunc('month', c.cal_date)
), sip AS (
    SELECT pr.direct_code,
           COUNT(*) AS n_installments,
           SUM(p.sip_amount / nd.nav) AS direct_units,
           SUM(p.sip_amount / nr.nav) AS regular_units
    FROM pairs pr
    CROSS JOIN sip_months m
    CROSS JOIN p
    JOIN nav_filled nd ON nd.scheme_code = pr.direct_code AND nd.nav_date = m.sip_date
    JOIN nav_filled nr ON nr.scheme_code = pr.regular_code AND nr.nav_date = m.sip_date
    WHERE m.sip_date - nd.source_date <= 7 AND m.sip_date - nr.source_date <= 7
    GROUP BY pr.direct_code
), gap AS (
    SELECT pr.*, cs.start_date, l.end_date,
           ds.nav AS direct_start, rs.nav AS regular_start,
           de.nav AS direct_end, re.nav AS regular_end
    FROM pairs pr
    CROSS JOIN last_day l
    CROSS JOIN p
    CROSS JOIN LATERAL (
        SELECT MIN(c.cal_date) AS start_date FROM trading_calendar c
        WHERE c.cal_date >= GREATEST(pr.common_first_date,
                                     (l.end_date - make_interval(years => p.years))::date)
    ) cs
    JOIN nav_filled ds ON ds.scheme_code = pr.direct_code AND ds.nav_date = cs.start_date
    JOIN nav_filled rs ON rs.scheme_code = pr.regular_code AND rs.nav_date = cs.start_date
    JOIN nav_filled de ON de.scheme_code = pr.direct_code AND de.nav_date = l.end_date
    JOIN nav_filled re ON re.scheme_code = pr.regular_code AND re.nav_date = l.end_date
    WHERE l.end_date - cs.start_date >= 365
      AND cs.start_date - LEAST(ds.source_date, rs.source_date) <= 7
      AND l.end_date - LEAST(de.source_date, re.source_date) <= 7
)
SELECT g.base_scheme_key,
       g.category,
       g.direct_code,
       g.direct_name,
       g.regular_code,
       g.regular_name,
       g.start_date,
       g.end_date,
       (g.end_date - g.start_date) / 365.25 AS years_compared,
       POWER(g.direct_end / g.direct_start, 365.0 / (g.end_date - g.start_date)) - 1 AS direct_cagr,
       POWER(g.regular_end / g.regular_start, 365.0 / (g.end_date - g.start_date)) - 1 AS regular_cagr,
       POWER(g.direct_end / g.direct_start, 365.0 / (g.end_date - g.start_date))
         - POWER(g.regular_end / g.regular_start, 365.0 / (g.end_date - g.start_date)) AS annual_gap,
       CASE WHEN s.n_installments = p.years * 12 THEN s.n_installments * p.sip_amount END AS sip_invested,
       CASE WHEN s.n_installments = p.years * 12 THEN s.direct_units * g.direct_end END AS sip_direct_value,
       CASE WHEN s.n_installments = p.years * 12 THEN s.regular_units * g.regular_end END AS sip_regular_value,
       CASE WHEN s.n_installments = p.years * 12
            THEN s.direct_units * g.direct_end - s.regular_units * g.regular_end END AS sip_rupee_gap
FROM gap g
CROSS JOIN p
LEFT JOIN sip s ON s.direct_code = g.direct_code;
CREATE UNIQUE INDEX ON direct_regular_gap (direct_code);
