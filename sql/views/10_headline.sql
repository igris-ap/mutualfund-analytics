-- The numbers quoted in reports/findings.md and on the dashboard's headline page.
-- One row, so the report and the app can't drift apart.
DROP MATERIALIZED VIEW IF EXISTS headline CASCADE;
CREATE MATERIALIZED VIEW headline AS
WITH d5 AS (SELECT * FROM category_summary WHERE category = 'All' AND plan_type = 'direct' AND window_years = 5),
     r5 AS (SELECT * FROM category_summary WHERE category = 'All' AND plan_type = 'regular' AND window_years = 5),
     gap AS (
         SELECT COUNT(*) AS n_pairs,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY annual_gap) AS median_annual_gap,
                COUNT(sip_rupee_gap) AS n_pairs_with_sip,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY sip_rupee_gap) AS median_sip_rupee_gap,
                MAX(sip_invested) AS sip_invested
         FROM direct_regular_gap
     )
SELECT d5.share_funds_beating AS direct_share_beating_5y,      -- the big number
       d5.n_funds AS direct_funds_5y,
       d5.pooled_beat_rate AS direct_beat_rate_5y,
       d5.median_fund_excess AS direct_median_excess_5y,
       r5.share_funds_beating AS regular_share_beating_5y,
       r5.pooled_beat_rate AS regular_beat_rate_5y,
       r5.median_fund_excess AS regular_median_excess_5y,
       gap.n_pairs,
       gap.median_annual_gap,
       gap.n_pairs_with_sip,
       gap.median_sip_rupee_gap,
       gap.sip_invested,
       (SELECT MAX(cal_date) FROM trading_calendar) AS data_as_of
FROM d5, r5, gap;
