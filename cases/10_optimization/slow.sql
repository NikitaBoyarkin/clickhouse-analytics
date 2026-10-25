-- Case 10 SLOW: "product 42 daily revenue report" — the query an analyst sends to prod.
--
-- Table ORDER BY key is (event_date, user_id): product_id is NOT in the primary key
-- and the data is not clustered by it, so ClickHouse must read every granule of the
-- amount/product_id/event_type columns across all 6 monthly partitions.
SELECT event_date,
       count() AS orders,
       round(sum(amount), 2) AS revenue
FROM events
WHERE product_id = 42
  AND event_type = 4
GROUP BY event_date
ORDER BY event_date;