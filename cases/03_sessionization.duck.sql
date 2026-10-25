-- DuckDB reference for 03 — plain lag() instead of lagInFrame(), same 30-minute rule.
WITH marked AS (
    SELECT user_id, event_ts,
           CASE WHEN event_ts - lag(event_ts, 1, TIMESTAMP '1970-01-01')
                     OVER (PARTITION BY user_id ORDER BY event_ts) > INTERVAL 30 MINUTE
                THEN 1 ELSE 0 END AS is_new
    FROM events
),
sessioned AS (
    SELECT user_id, event_ts,
           sum(is_new) OVER (PARTITION BY user_id ORDER BY event_ts) AS session_no
    FROM marked
),
sessions AS (
    SELECT user_id, session_no,
           date_diff('second', min(event_ts), max(event_ts)) AS dur_sec,
           count() AS events
    FROM sessioned
    GROUP BY user_id, session_no
)
SELECT count() AS sessions,
       count(DISTINCT user_id) AS users,
       round(avg(events), 2) AS avg_events_per_session,
       round(avg(dur_sec) / 60, 2) AS avg_session_min,
       round(quantile_cont(dur_sec, 0.95) / 60, 2) AS p95_session_min
FROM sessions;