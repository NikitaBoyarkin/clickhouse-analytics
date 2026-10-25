-- DuckDB reference for 02 — independent engine, same semantics (Monday-start weeks).
-- Run by scripts/run.py against data/seed.parquet; a divergence means one of the
-- two dialects changed meaning, not that one engine is "wrong".
WITH first_seen AS (
    SELECT user_id, CAST(date_trunc('week', min(event_date)) AS DATE) AS cohort
    FROM events GROUP BY user_id
    HAVING date_trunc('week', min(event_date)) BETWEEN DATE '2025-07-07' AND DATE '2025-10-06'
),
activity AS (
    SELECT DISTINCT user_id, CAST(date_trunc('week', event_date) AS DATE) AS act_week FROM events
)
SELECT f.cohort,
       date_diff('week', f.cohort, a.act_week) AS week_no,
       count(DISTINCT a.user_id) AS users
FROM activity a
JOIN first_seen f USING (user_id)
WHERE a.act_week >= f.cohort
  AND date_diff('week', f.cohort, a.act_week) BETWEEN 0 AND 4
GROUP BY f.cohort, week_no
ORDER BY f.cohort, week_no;