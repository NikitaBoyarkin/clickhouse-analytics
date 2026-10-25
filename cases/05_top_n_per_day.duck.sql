-- DuckDB reference for 05 — ROW_NUMBER + QUALIFY (DuckDB/Postgres idiom) vs CH LIMIT BY.
WITH daily AS (
    SELECT event_date, product_id, round(sum(amount), 2) AS revenue
    FROM events
    WHERE event_type = 4
    GROUP BY event_date, product_id
)
SELECT event_date, product_id, revenue
FROM daily
QUALIFY row_number() OVER (PARTITION BY event_date ORDER BY revenue DESC) <= 3
ORDER BY event_date, revenue DESC;