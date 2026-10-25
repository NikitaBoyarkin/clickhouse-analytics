-- 03: sessionization — new session after a 30-minute gap of inactivity.
-- ClickHouse-specific: lagInFrame + running sum over the ordered partition.
-- (In CH the "running total" idiom is sum() OVER (ORDER BY ...), which needs the
--  window frame to include the current row — that is the default here.)
WITH marked AS (
    SELECT user_id, event_ts,
           if(event_ts - lagInFrame(event_ts, 1, toDateTime(0))
              OVER (PARTITION BY user_id ORDER BY event_ts) > 1800, 1, 0) AS is_new
    FROM events
),
sessioned AS (
    SELECT user_id, event_ts,
           sum(is_new) OVER (PARTITION BY user_id ORDER BY event_ts) AS session_no
    FROM marked
),
sessions AS (
    SELECT user_id, session_no,
           dateDiff('second', min(event_ts), max(event_ts)) AS dur_sec,
           count() AS events
    FROM sessioned
    GROUP BY user_id, session_no
)
SELECT count() AS sessions,
       count(DISTINCT user_id) AS users,
       round(avg(events), 2) AS avg_events_per_session,
       round(avg(dur_sec) / 60, 2) AS avg_session_min,
       round(quantileExact(0.95)(dur_sec) / 60, 2) AS p95_session_min
FROM sessions;