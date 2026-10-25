-- DuckDB reference for 06 — same 30-day window, same zero-spender denominator.
WITH first_seen AS (
    SELECT user_id, min(event_date) AS d0 FROM events GROUP BY user_id
),
orders AS (
    SELECT e.user_id, sum(e.amount) AS spend
    FROM events e
    JOIN first_seen f USING (user_id)
    WHERE e.event_type = 4
      AND date_diff('day', f.d0, e.event_date) < 30
    GROUP BY e.user_id
)
SELECT CAST(date_trunc('week', f.d0) AS DATE) AS cohort,
       count() AS users,
       count(o.spend) AS payers,
       round(count(o.spend) / count() * 100, 2) AS payer_pct,
       round(avg(coalesce(o.spend, 0)), 2) AS ltv30_per_user,
       round(avg(o.spend), 2) AS aov_30d
FROM first_seen f
LEFT JOIN orders o USING (user_id)
GROUP BY cohort
ORDER BY cohort;