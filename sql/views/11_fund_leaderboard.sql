-- One row per active-fund plan with every metric, for the leaderboard and report card.
DROP MATERIALIZED VIEW IF EXISTS fund_leaderboard CASCADE;
CREATE MATERIALIZED VIEW fund_leaderboard AS
SELECT sc.scheme_code,
       sc.scheme_name,
       sc.fund_house,
       sc.category,
       sc.plan_type,
       sc.first_nav_date,
       sc.last_nav_date,
       sc.last_nav_date >= (SELECT MAX(cal_date) FROM trading_calendar) - 7 AS is_active,
       b3.n_windows AS windows_3y,
       b3.beat_rate AS beat_rate_3y,
       b3.median_excess AS median_excess_3y,
       b5.n_windows AS windows_5y,
       b5.beat_rate AS beat_rate_5y,
       b5.median_excess AS median_excess_5y,
       rm.cagr AS cagr_trailing,
       rm.volatility,
       rm.sharpe,
       rm.sortino,
       rm.max_drawdown,
       g.annual_gap AS direct_regular_gap,
       g.sip_rupee_gap
FROM schemes sc
LEFT JOIN fund_beat_rates b3 ON b3.scheme_code = sc.scheme_code AND b3.window_years = 3
LEFT JOIN fund_beat_rates b5 ON b5.scheme_code = sc.scheme_code AND b5.window_years = 5
LEFT JOIN risk_metrics rm ON rm.scheme_code = sc.scheme_code
LEFT JOIN direct_regular_gap g ON sc.scheme_code IN (g.direct_code, g.regular_code)
WHERE NOT sc.is_benchmark;
CREATE UNIQUE INDEX ON fund_leaderboard (scheme_code);
