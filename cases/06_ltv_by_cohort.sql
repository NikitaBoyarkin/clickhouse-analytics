-- 06: LTV-30 by cohort — average revenue per user in the first 30 days,
-- including users who never purchased (they contribute 0, which is the honest
-- denominator; averaging over payers only is the classic LTV overstatement).
WITH first_seen AS (
    SELECT user_id, min(event_date) AS d0 FROM events GROUP BY user_id
),
orders AS (
    SELECT e.user_id, sum(e.amount) AS spend
    FROM events e
    JOIN first_seen f USING (user_id)
    WHERE e.event_type = 4
      AND e.event_date - f.d0 < 30
    GROUP BY e.user_id
)
SELECT toStartOfWeek(f.d0, 1) AS cohort,
       count() AS users,
       count(o.spend) AS payers,
       round(count(o.spend) / count() * 100, 2) AS payer_pct,
       round(avg(coalesce(o.spend, 0)), 2) AS ltv30_per_user,
       round(avg(o.spend), 2) AS aov_30d
FROM first_seen f
LEFT JOIN orders o USING (user_id)
GROUP BY cohort
ORDER BY cohort
-- ClickHouse gotcha: a LEFT JOIN fills unmatched rows with type defaults, NOT NULL
-- (join_use_nulls = 0 by default). Without this, count(o.spend) counts every user as a
-- payer and payer_pct is a flat 100%. avg(coalesce(...)) hides it — this setting does not.
SETTINGS join_use_nulls = 1;