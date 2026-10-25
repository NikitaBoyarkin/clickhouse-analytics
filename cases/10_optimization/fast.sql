-- Case 10 FAST: the query text is deliberately IDENTICAL to slow.sql.
--
-- That is the point of the case: the ~100x win here is not a query rewrite, it is a
-- schema-side object (projection, see fix.sql). Measure both, then check EXPLAIN:
-- after MATERIALIZE PROJECTION the planner rewrites the same SQL to read
-- `events.p_product`, which is physically ordered by product_id — so only the granules
-- holding product 42 are touched instead of all 50M rows.
SELECT event_date,
       count() AS orders,
       round(sum(amount), 2) AS revenue
FROM events
WHERE product_id = 42
  AND event_type = 4
GROUP BY event_date
ORDER BY event_date;