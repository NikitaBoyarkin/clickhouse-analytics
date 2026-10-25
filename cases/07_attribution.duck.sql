-- DuckDB reference for 07 — min_by/max_by instead of argMin/argMax, FILTER for the sum.
WITH touch AS (
    SELECT user_id,
           min_by(channel, (event_ts, channel)) AS first_touch,
           max_by(channel, (event_ts, channel)) AS last_touch,
           sum(amount) FILTER (WHERE event_type = 4) AS revenue
    FROM events
    GROUP BY user_id
)
SELECT model, channel, round(sum(revenue), 2) AS revenue, count() AS users
FROM (
    SELECT 'first_touch' AS model, first_touch AS channel, revenue FROM touch
    UNION ALL
    SELECT 'last_touch' AS model, last_touch AS channel, revenue FROM touch
)
GROUP BY model, channel
ORDER BY channel, model;