-- DuckDB reference for 08 — same row_number terciles; CASE instead of if().
WITH base AS (
    SELECT user_id,
           date_diff('day', max(event_date) FILTER (WHERE event_type = 4), DATE '2025-12-27') AS recency_days,
           count(*) FILTER (WHERE event_type = 4) AS frequency,
           sum(amount) FILTER (WHERE event_type = 4) AS monetary
    FROM events
    GROUP BY user_id
    HAVING count(*) FILTER (WHERE event_type = 4) > 0
),
ranked AS (
    SELECT *,
           row_number() OVER (ORDER BY recency_days, user_id) AS r_rank,
           row_number() OVER (ORDER BY frequency DESC, monetary DESC, user_id) AS f_rank,
           row_number() OVER (ORDER BY monetary DESC, user_id) AS m_rank,
           count() OVER () AS total
    FROM base
)
SELECT CASE WHEN r_rank * 3 <= total THEN 'recent'
            WHEN r_rank * 3 <= 2 * total THEN 'mid' ELSE 'stale' END AS recency_b,
       CASE WHEN f_rank * 3 <= total THEN 'high'
            WHEN f_rank * 3 <= 2 * total THEN 'mid' ELSE 'low' END AS frequency_b,
       CASE WHEN m_rank * 3 <= total THEN 'high'
            WHEN m_rank * 3 <= 2 * total THEN 'mid' ELSE 'low' END AS monetary_b,
       count() AS users,
       round(avg(monetary), 2) AS avg_monetary
FROM ranked
GROUP BY recency_b, frequency_b, monetary_b
ORDER BY recency_b, frequency_b, monetary_b;