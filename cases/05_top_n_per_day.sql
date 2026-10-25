-- 05: top-3 products by revenue, per day.
-- ClickHouse-native: LIMIT N BY — a per-group top-N with no window function at all.
-- Interview angle: DuckDB/Postgres need ROW_NUMBER + QUALIFY/subquery; LIMIT BY is
-- cheaper (bounded heaps per group, no full sort) and is a common CH code-review point.
SELECT event_date,
       product_id,
       round(sum(amount), 2) AS revenue
FROM events
WHERE event_type = 4
GROUP BY event_date, product_id
ORDER BY event_date, revenue DESC
LIMIT 3 BY event_date;