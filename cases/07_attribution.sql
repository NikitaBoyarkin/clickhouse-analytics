-- 07: first-touch vs last-touch channel attribution of user revenue.
-- ClickHouse-native: argMin / argMax (any aggregate can be "the value at the min/max
-- of another column") — no self-join, no window, one pass over 50M rows.
WITH touch AS (
    SELECT user_id,
           -- (event_ts, channel) is a minimal deterministic ordering key: same-second
           -- ties are broken by channel, and a full tie yields the same channel anyway.
           -- A 4-field tuple key works too but makes the aggregate far heavier
           -- (measured: 7.3 GiB on 1M groups vs ~1 GiB here).
           argMin(channel, (event_ts, channel)) AS first_touch,
           argMax(channel, (event_ts, channel)) AS last_touch,
           sumIf(amount, event_type = 4) AS revenue
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