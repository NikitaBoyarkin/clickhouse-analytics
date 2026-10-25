-- 04: gaps-and-islands — longest consecutive-day activity streak per user.
-- Trick: (date - row_number()) is constant inside a streak, so it identifies the island.
-- ClickHouse: Date minus UInt is a Date shift, so no INTERVAL arithmetic is needed.
WITH days AS (
    SELECT DISTINCT user_id, event_date FROM events
),
grp AS (
    SELECT user_id, event_date,
           event_date - row_number() OVER (PARTITION BY user_id ORDER BY event_date) AS island
    FROM days
),
streaks AS (
    SELECT user_id, count() AS streak_days, min(event_date) AS streak_start
    FROM grp
    GROUP BY user_id, island
)
SELECT user_id, streak_days, streak_start
FROM streaks
ORDER BY streak_days DESC, user_id
LIMIT 10;