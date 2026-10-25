-- 01: 1-day conversion funnel: visit(1) -> cart(2) -> checkout(3) -> purchase(4)
-- ClickHouse-native: windowFunnel — sliding 86400s window, single pass, per user.
-- Why it matters in interviews: this is the "do you know CH" question. DuckDB needs
-- a self-join or recursive CTE for the same semantics; CH does it in one aggregate.
WITH f AS (
    SELECT user_id,
           windowFunnel(86400)(event_ts, event_type = 1, event_type = 2,
                               event_type = 3, event_type = 4) AS step
    FROM events
    GROUP BY user_id
)
SELECT step AS steps_reached, count() AS users
FROM f
GROUP BY step
ORDER BY step;