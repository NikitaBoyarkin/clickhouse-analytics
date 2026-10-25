-- 02: weekly retention matrix — cohort = week of first activity, activity week = same week
-- offset. Rows are cohorts (Monday-start weeks), columns week_no 0..4.
-- Caveat baked into the query: cohorts near the end of the data window cannot reach
-- week_no 4 (truncation) — that is why the cohort range is bounded explicitly.
WITH first_seen AS (
    SELECT user_id, toStartOfWeek(min(event_date), 1) AS cohort
    FROM events
    GROUP BY user_id
    HAVING cohort BETWEEN toDate('2025-07-07') AND toDate('2025-10-06')
),
activity AS (
    SELECT DISTINCT user_id, toStartOfWeek(event_date, 1) AS act_week
    FROM events
)
SELECT f.cohort,
       dateDiff('week', f.cohort, a.act_week) AS week_no,
       count(DISTINCT a.user_id) AS users
FROM activity a
JOIN first_seen f USING (user_id)
WHERE a.act_week >= f.cohort
  AND dateDiff('week', f.cohort, a.act_week) BETWEEN 0 AND 4
GROUP BY f.cohort, week_no
ORDER BY f.cohort, week_no;